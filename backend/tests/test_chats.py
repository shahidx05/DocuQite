"""
tests/test_chats.py — Phase 5B tests for chat sessions, message history, and follow-up rewriting.

Coverage:
- Create, list, get, delete chat sessions
- Cascade deletion of messages when session is deleted
- Messages saved and returned in chronological order
- Cross-user isolation: User B in the same workspace gets 404 for User A's session
- Non-member gets 404 on all endpoints
- First message skips rewrite; title updated to first 60 characters
- Second message triggers rewrite
- Rewrite failure falls back safely to original question
- Abstained answers saved with abstained=True
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.services.embedding_service as emb_mod
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.rag import rewrite
from app.schemas.ask import AskResponse, AskTimings, AskTokens, Citation
from app.services.vector_service import delete_by_workspace, ensure_collection, upsert_chunks

TEST_COLLECTION = "rag_chunks_test"
FAKE_DIM = 384


def _fake_dense(text: str) -> list[float]:
    return [0.1] * FAKE_DIM


def _fake_sparse(text: str) -> dict:
    return {"indices": [0, 1, 2], "values": [0.5, 0.3, 0.2]}


class _FakeChunk:
    def __init__(self, workspace_id, document_id=None, page_number=1,
                 section_title="Security", text="We protect your personal data.", chunk_index=0):
        self.id = uuid.uuid4()
        self.document_id = document_id or uuid.uuid4()
        self.workspace_id = workspace_id
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.section_title = section_title
        self.text = text


@pytest.fixture(scope="module", autouse=True)
def ensure_test_collection():
    ensure_collection(TEST_COLLECTION)


@pytest.fixture()
def chat_env(monkeypatch, db):
    """Setup test users, workspaces, and mock configuration."""
    monkeypatch.setattr(settings, "QDRANT_COLLECTION", TEST_COLLECTION)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    monkeypatch.setattr(emb_mod, "embed_query", _fake_dense)
    monkeypatch.setattr(emb_mod, "sparse_query", _fake_sparse)
    monkeypatch.setattr("app.services.retrieval_service.embedding_service.embed_query", _fake_dense)
    monkeypatch.setattr("app.services.retrieval_service.embedding_service.sparse_query", _fake_sparse)

    class _HighScoreEncoder:
        def rerank(self, query, documents, **kwargs):
            return [5.5] * len(documents)

    monkeypatch.setattr("app.services.reranking_service._get_cross_encoder", lambda: _HighScoreEncoder())
    monkeypatch.setattr("app.services.retrieval_service.reranking_service._get_cross_encoder", lambda: _HighScoreEncoder())

    # 1. Create User A (owner)
    user_a = User(
        name="User A",
        email=f"usera_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password123"),
        role="user",
    )
    # 2. Create User B (member of same workspace)
    user_b = User(
        name="User B",
        email=f"userb_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password123"),
        role="user",
    )
    # 3. Create User C (non-member)
    user_c = User(
        name="User C",
        email=f"userc_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password123"),
        role="user",
    )
    db.add_all([user_a, user_b, user_c])
    db.commit()

    # Create workspace owned by User A
    ws = Workspace(name="Chat Test Workspace", owner_id=user_a.id)
    db.add(ws)
    db.commit()

    # Add User A as owner member, User B as regular member
    mem_a = WorkspaceMember(workspace_id=ws.id, user_id=user_a.id, role="owner")
    mem_b = WorkspaceMember(workspace_id=ws.id, user_id=user_b.id, role="member")
    db.add_all([mem_a, mem_b])
    db.commit()

    # Seed chunk into Qdrant for RAG retrieval
    doc_id = uuid.uuid4()
    chunks = [
        _FakeChunk(ws.id, doc_id, page_number=1, section_title="Data Retention", text="We retain data for 30 days.")
    ]
    upsert_chunks(
        chunks_db=chunks,
        document_name="policy.pdf",
        dense_vecs=[[0.1] * FAKE_DIM],
        sparse_vecs=[{"indices": [0, 1], "values": [0.5, 0.5]}],
        collection_name=TEST_COLLECTION,
    )

    token_a = create_access_token(str(user_a.id))
    token_b = create_access_token(str(user_b.id))
    token_c = create_access_token(str(user_c.id))

    yield {
        "user_a": user_a,
        "user_b": user_b,
        "user_c": user_c,
        "workspace": ws,
        "token_a": token_a,
        "token_b": token_b,
        "token_c": token_c,
    }

    delete_by_workspace(ws.id, collection_name=TEST_COLLECTION)


# ═══════════════════════════════════════════════════════════════════════════════
# Session CRUD & Isolation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatSessionCRUD:
    def test_create_and_list_sessions(self, client, chat_env):
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        # Create session with default title
        res = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers)
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == "New Chat"
        assert data["workspace_id"] == str(ws_id)
        assert data["user_id"] == str(chat_env["user_a"].id)
        session_id = data["id"]

        # Create session with custom title
        res2 = client.post(
            f"/api/workspaces/{ws_id}/chats",
            headers=headers,
            json={"title": "Custom Session"},
        )
        assert res2.status_code == 201
        assert res2.json()["title"] == "Custom Session"

        # List sessions
        list_res = client.get(f"/api/workspaces/{ws_id}/chats", headers=headers)
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) == 2
        ids = [item["id"] for item in items]
        assert session_id in ids

    def test_get_session_details(self, client, chat_env):
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        create_res = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers)
        chat_id = create_res.json()["id"]

        get_res = client.get(f"/api/chats/{chat_id}", headers=headers)
        assert get_res.status_code == 200
        detail = get_res.json()
        assert detail["id"] == chat_id
        assert detail["messages"] == []

    def test_delete_session_and_cascade_messages(self, client, chat_env, db):
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        # Create session
        create_res = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers)
        chat_id = uuid.UUID(create_res.json()["id"])

        # Add message directly in DB
        msg = ChatMessage(session_id=chat_id, role="user", content="Test message")
        db.add(msg)
        db.commit()

        # Delete session via API
        del_res = client.delete(f"/api/chats/{chat_id}", headers=headers)
        assert del_res.status_code == 204

        # Verify session and message are gone
        assert db.get(ChatSession, chat_id) is None
        assert db.query(ChatMessage).filter(ChatMessage.session_id == chat_id).count() == 0

    def test_user_b_cannot_see_user_a_session_in_same_workspace(self, client, chat_env):
        """User B in the same workspace receives 404 when trying to access User A's session."""
        ws_id = chat_env["workspace"].id
        headers_a = {"Authorization": f"Bearer {chat_env['token_a']}"}
        headers_b = {"Authorization": f"Bearer {chat_env['token_b']}"}

        # User A creates session
        create_res = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers_a)
        chat_id = create_res.json()["id"]

        # User B listing sessions in the workspace should see 0 sessions
        list_b = client.get(f"/api/workspaces/{ws_id}/chats", headers=headers_b)
        assert list_b.status_code == 200
        assert len(list_b.json()) == 0

        # User B attempting GET on User A's session gets 404
        get_b = client.get(f"/api/chats/{chat_id}", headers=headers_b)
        assert get_b.status_code == 404

        # User B attempting DELETE on User A's session gets 404
        del_b = client.delete(f"/api/chats/{chat_id}", headers=headers_b)
        assert del_b.status_code == 404

        # User B attempting POST messages on User A's session gets 404
        post_b = client.post(f"/api/chats/{chat_id}/messages", headers=headers_b, json={"question": "hi"})
        assert post_b.status_code == 404

    def test_non_member_cannot_access_any_chats(self, client, chat_env):
        """User C (not in workspace) gets 404 across all endpoints."""
        ws_id = chat_env["workspace"].id
        headers_a = {"Authorization": f"Bearer {chat_env['token_a']}"}
        headers_c = {"Authorization": f"Bearer {chat_env['token_c']}"}

        # Non-member cannot create session in workspace
        res = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers_c)
        assert res.status_code == 404

        # Non-member cannot list sessions in workspace
        res_list = client.get(f"/api/workspaces/{ws_id}/chats", headers=headers_c)
        assert res_list.status_code == 404

        # Create session with User A
        create_res = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers_a)
        chat_id = create_res.json()["id"]

        # Non-member cannot get or message session
        assert client.get(f"/api/chats/{chat_id}", headers=headers_c).status_code == 404
        assert client.post(f"/api/chats/{chat_id}/messages", headers=headers_c, json={"question": "q"}).status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Messaging, Ordering, and Query Rewriting Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestChatMessagingAndRewriting:
    def test_first_message_skips_rewrite_and_updates_title(self, client, chat_env, monkeypatch):
        """First message skips rewrite_question call and sets session title to first 60 chars."""
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        session = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers).json()
        chat_id = session["id"]

        rewrite_called = False

        def spy_rewrite(*args, **kwargs):
            nonlocal rewrite_called
            rewrite_called = True
            return args[0]

        monkeypatch.setattr("app.api.routes.chats.rewrite_question", spy_rewrite)

        long_q = "What personal information do you collect when registering an account?"
        msg_res = client.post(
            f"/api/chats/{chat_id}/messages",
            headers=headers,
            json={"question": long_q},
        )
        assert msg_res.status_code == 200
        assert not rewrite_called, "Rewrite should NOT be called on the first message."

        data = msg_res.json()
        assert data["role"] == "assistant"
        assert "[1]" in data["content"]
        assert data["metadata"]["rewritten_question"] == long_q

        # Verify chat title updated to first 60 chars
        session_detail = client.get(f"/api/chats/{chat_id}", headers=headers).json()
        assert session_detail["title"] == long_q[:60].strip()

    def test_second_message_calls_rewrite(self, client, chat_env, monkeypatch):
        """Subsequent messages call rewrite_question with recent conversation history."""
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        session = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers).json()
        chat_id = session["id"]

        # Message 1
        client.post(
            f"/api/chats/{chat_id}/messages",
            headers=headers,
            json={"question": "what data do you collect"},
        )

        rewrite_calls = []

        def tracked_rewrite(question, history):
            rewrite_calls.append((question, len(history)))
            return f"rewritten: {question}"

        monkeypatch.setattr("app.api.routes.chats.rewrite_question", tracked_rewrite)

        # Message 2
        msg2_res = client.post(
            f"/api/chats/{chat_id}/messages",
            headers=headers,
            json={"question": "and how long do you keep it"},
        )
        assert msg2_res.status_code == 200
        assert len(rewrite_calls) == 1
        assert rewrite_calls[0][0] == "and how long do you keep it"
        assert rewrite_calls[0][1] == 2  # Prior user + assistant message

        data = msg2_res.json()
        assert data["metadata"]["rewritten_question"] == "rewritten: and how long do you keep it"

    def test_messages_saved_in_chronological_order(self, client, chat_env):
        """User and assistant messages are stored and retrieved in exact chronological order."""
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        session = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers).json()
        chat_id = session["id"]

        client.post(f"/api/chats/{chat_id}/messages", headers=headers, json={"question": "question 1"})
        client.post(f"/api/chats/{chat_id}/messages", headers=headers, json={"question": "question 2"})

        detail = client.get(f"/api/chats/{chat_id}", headers=headers).json()
        msgs = detail["messages"]
        assert len(msgs) == 4
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "question 1"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["role"] == "user"
        assert msgs[2]["content"] == "question 2"
        assert msgs[3]["role"] == "assistant"

    def test_rewrite_failure_falls_back_safely(self, client, chat_env, monkeypatch):
        """If rewrite_question encounters an error, it falls back to original question and succeeds."""
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        session = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers).json()
        chat_id = session["id"]

        # Message 1
        client.post(f"/api/chats/{chat_id}/messages", headers=headers, json={"question": "question 1"})

        # Force get_llm in rewrite to throw an unexpected exception
        def faulty_get_llm():
            raise RuntimeError("LLM service unavailable")

        monkeypatch.setattr("app.rag.rewrite.get_llm", faulty_get_llm)

        msg2_res = client.post(
            f"/api/chats/{chat_id}/messages",
            headers=headers,
            json={"question": "question 2"},
        )
        assert msg2_res.status_code == 200
        # Check that original question was preserved as fallback
        assert msg2_res.json()["metadata"]["rewritten_question"] == "question 2"

    def test_abstained_answers_are_saved_with_abstained_true(self, client, chat_env, monkeypatch):
        """When generation abstains, message is saved with abstained=True and empty citations."""
        ws_id = chat_env["workspace"].id
        headers = {"Authorization": f"Bearer {chat_env['token_a']}"}

        session = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers).json()
        chat_id = session["id"]

        # Mock generation.answer to return abstained response
        def mock_abstain(workspace_id, question, collection_name=None):
            return AskResponse(
                answer="I couldn't find enough information in the uploaded documents to answer this question.",
                abstained=True,
                citations=[],
                timings=AskTimings(retrieval_ms=10, llm_ms=0, total_ms=10),
                tokens=AskTokens(input_tokens=0, output_tokens=0),
            )

        monkeypatch.setattr("app.api.routes.chats.answer", mock_abstain)

        msg_res = client.post(
            f"/api/chats/{chat_id}/messages",
            headers=headers,
            json={"question": "who won the 2018 world cup"},
        )
        assert msg_res.status_code == 200
        data = msg_res.json()
        assert data["abstained"] is True
        assert data["citations"] is None or data["citations"] == []

        # Verify saved in DB
        detail = client.get(f"/api/chats/{chat_id}", headers=headers).json()
        assistant_msg = detail["messages"][1]
        assert assistant_msg["abstained"] is True
