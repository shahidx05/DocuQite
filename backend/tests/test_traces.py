"""
tests/test_traces.py — Phase 6 tests for request tracing and LLM metrics.

Covers:
- Trace saved for /ask and for chat messages
- Abstained request saves trace with llm_ms=0 and zero tokens
- Tracing failure does not break the user request
- Traces contain no answer or document text (only question_length)
- Metrics math (p50/p95, abstain rate, tokens_per_second) on known fixture data
- Workspace isolation (traces in A never leak into B)
- Non-member gets 404
- Empty workspace metrics returns zeroed metrics without crashing
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.services.embedding_service as emb_mod
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.trace import RequestTrace
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import tracing_service
from app.services.vector_service import delete_by_workspace, ensure_collection, upsert_chunks

TEST_COLLECTION = "rag_chunks_test"
FAKE_DIM = 384


def _fake_dense(text: str) -> list[float]:
    return [0.1] * FAKE_DIM


def _fake_sparse(text: str) -> dict:
    return {"indices": [0, 1, 2], "values": [0.5, 0.3, 0.2]}


class _FakeChunk:
    def __init__(self, workspace_id, document_id=None, page_number=1,
                 section_title="Privacy", text="We retain data for 30 days.", chunk_index=0):
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
def trace_env(monkeypatch, db):
    """Setup test users, workspaces, mock cross-encoder and mock embeddings."""
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

    # User A (owner of Workspace A)
    user_a = User(
        name="User A",
        email=f"usera_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password123"),
        role="user",
    )
    # User B (owner of Workspace B)
    user_b = User(
        name="User B",
        email=f"userb_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password123"),
        role="user",
    )
    # User C (non-member)
    user_c = User(
        name="User C",
        email=f"userc_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("password123"),
        role="user",
    )
    db.add_all([user_a, user_b, user_c])
    db.commit()

    ws_a = Workspace(name="Workspace A", owner_id=user_a.id)
    ws_b = Workspace(name="Workspace B", owner_id=user_b.id)
    db.add_all([ws_a, ws_b])
    db.commit()

    mem_a = WorkspaceMember(workspace_id=ws_a.id, user_id=user_a.id, role="owner")
    mem_b = WorkspaceMember(workspace_id=ws_b.id, user_id=user_b.id, role="owner")
    db.add_all([mem_a, mem_b])
    db.commit()

    # Seed chunk for Workspace A
    doc_id = uuid.uuid4()
    chunks = [
        _FakeChunk(ws_a.id, doc_id, page_number=1, section_title="Policy", text="We retain data for 30 days.")
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
        "ws_a": ws_a,
        "ws_b": ws_b,
        "token_a": token_a,
        "token_b": token_b,
        "token_c": token_c,
    }

    delete_by_workspace(ws_a.id, collection_name=TEST_COLLECTION)
    delete_by_workspace(ws_b.id, collection_name=TEST_COLLECTION)


# ═══════════════════════════════════════════════════════════════════════════════
# Tracing Instrumentation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTracingPipeline:
    def test_trace_saved_for_ask(self, client, trace_env):
        ws_id = trace_env["ws_a"].id
        headers = {"Authorization": f"Bearer {trace_env['token_a']}"}

        q = "how do you protect data?"
        res = client.post(f"/api/workspaces/{ws_id}/ask", headers=headers, json={"question": q})
        assert res.status_code == 200

        # Check trace via API
        traces_res = client.get(f"/api/workspaces/{ws_id}/traces", headers=headers)
        assert traces_res.status_code == 200
        traces = traces_res.json()
        assert len(traces) == 1

        t = traces[0]
        assert t["workspace_id"] == str(ws_id)
        assert t["user_id"] == str(trace_env["user_a"].id)
        assert t["source"] == "ask"
        assert t["provider"] == "mock"
        assert t["question_length"] == len(q)
        assert t["total_ms"] >= 0
        assert t["input_tokens"] > 0
        assert t["output_tokens"] > 0
        assert t["abstained"] is False
        assert t["error"] is None

    def test_trace_saved_for_chat_message(self, client, trace_env):
        ws_id = trace_env["ws_a"].id
        headers = {"Authorization": f"Bearer {trace_env['token_a']}"}

        # Create chat session
        session = client.post(f"/api/workspaces/{ws_id}/chats", headers=headers).json()
        chat_id = session["id"]

        # Post message
        q = "how long do you keep data?"
        res = client.post(f"/api/chats/{chat_id}/messages", headers=headers, json={"question": q})
        assert res.status_code == 200

        # Check trace
        traces_res = client.get(f"/api/workspaces/{ws_id}/traces", headers=headers)
        assert traces_res.status_code == 200
        traces = traces_res.json()
        chat_traces = [tr for tr in traces if tr["source"] == "chat"]
        assert len(chat_traces) == 1
        ct = chat_traces[0]
        assert ct["question_length"] == len(q)
        assert ct["user_id"] == str(trace_env["user_a"].id)

    def test_abstained_request_saves_trace_with_zero_llm_and_tokens(self, client, trace_env, monkeypatch):
        """When a request abstains before LLM, trace records llm_ms=0 and 0 tokens."""
        ws_id = trace_env["ws_a"].id
        headers = {"Authorization": f"Bearer {trace_env['token_a']}"}

        # Mock cross-encoder with low score to trigger abstention
        class _LowScoreEncoder:
            def rerank(self, query, documents, **kwargs):
                return [-15.0] * len(documents)

        monkeypatch.setattr("app.services.reranking_service._get_cross_encoder", lambda: _LowScoreEncoder())
        monkeypatch.setattr("app.services.retrieval_service.reranking_service._get_cross_encoder", lambda: _LowScoreEncoder())

        res = client.post(f"/api/workspaces/{ws_id}/ask", headers=headers, json={"question": "who won 2018 world cup"})
        assert res.status_code == 200
        assert res.json()["abstained"] is True

        traces_res = client.get(f"/api/workspaces/{ws_id}/traces", headers=headers)
        t = traces_res.json()[0]
        assert t["abstained"] is True
        assert t["llm_ms"] == 0
        assert t["input_tokens"] == 0
        assert t["output_tokens"] == 0

    def test_tracing_failure_does_not_break_request(self, client, trace_env, monkeypatch):
        """If record_trace raises an exception, the user request still completes successfully."""
        ws_id = trace_env["ws_a"].id
        headers = {"Authorization": f"Bearer {trace_env['token_a']}"}

        def broken_record_trace(*args, **kwargs):
            raise RuntimeError("Database connection lost during tracing")

        monkeypatch.setattr(tracing_service, "record_trace", broken_record_trace)

        res = client.post(f"/api/workspaces/{ws_id}/ask", headers=headers, json={"question": "test question"})
        assert res.status_code == 200
        assert "answer" in res.json()

    def test_traces_contain_no_answer_or_document_text(self, db):
        """Ensure RequestTrace model has no columns for raw question, document text, or answer text."""
        columns = [c.name for c in RequestTrace.__table__.columns]
        assert "question_length" in columns
        assert "question" not in columns
        assert "text" not in columns
        assert "answer" not in columns
        assert "document_text" not in columns
        assert "content" not in columns


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Math & Isolation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetricsAndIsolation:
    def test_metrics_math_on_known_fixture_data(self):
        """Verify p50, p95, abstain rate, error rate, and tokens_per_second calculation."""
        traces = [
            RequestTrace(
                workspace_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                source="ask",
                provider="mock",
                model="mock",
                question_length=20,
                rewrite_ms=0,
                embed_ms=10,
                qdrant_ms=10,
                rerank_ms=10,
                llm_ms=100,
                total_ms=130,
                input_tokens=100,
                output_tokens=50,
                estimated_cost_usd=0.001,
                candidates_count=5,
                abstained=False,
            ),
            RequestTrace(
                workspace_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                source="chat",
                provider="mock",
                model="mock",
                question_length=25,
                rewrite_ms=20,
                embed_ms=20,
                qdrant_ms=20,
                rerank_ms=20,
                llm_ms=200,
                total_ms=280,
                input_tokens=200,
                output_tokens=100,
                estimated_cost_usd=0.002,
                candidates_count=5,
                abstained=False,
            ),
            RequestTrace(
                workspace_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                source="ask",
                provider="mock",
                model="mock",
                question_length=15,
                rewrite_ms=0,
                embed_ms=30,
                qdrant_ms=30,
                rerank_ms=30,
                llm_ms=0,
                total_ms=90,
                input_tokens=0,
                output_tokens=0,
                estimated_cost_usd=0.0,
                candidates_count=0,
                abstained=True,
            ),
            RequestTrace(
                workspace_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                source="ask",
                provider="mock",
                model="mock",
                question_length=30,
                rewrite_ms=0,
                embed_ms=40,
                qdrant_ms=40,
                rerank_ms=40,
                llm_ms=400,
                total_ms=520,
                input_tokens=400,
                output_tokens=200,
                estimated_cost_usd=0.004,
                candidates_count=5,
                abstained=False,
                error="Rate limit hit",
            ),
        ]

        metrics = tracing_service.compute_metrics(traces)

        assert metrics.request_count == 4
        # 1 of 4 abstained -> 0.25
        assert metrics.abstain_rate == 0.25
        # 1 of 4 errored -> 0.25
        assert metrics.error_rate == 0.25
        # total cost = 0.001 + 0.002 + 0.0 + 0.004 = 0.007
        assert round(metrics.total_estimated_cost_usd, 3) == 0.007
        # avg in = (100+200+0+400)/4 = 175.0
        assert metrics.avg_input_tokens == 175.0
        # avg out = (50+100+0+200)/4 = 87.5
        assert metrics.avg_output_tokens == 87.5
        # total output tokens = 350; total llm_ms = 700 ms = 0.70s -> 350 / 0.7 = 500.0 tokens/s
        assert metrics.tokens_per_second == 500.0

        # total_ms sorted: [90, 130, 280, 520]
        # p50 (idx = 3 * 0.5 = 1.5 -> avg(130, 280) = 205.0)
        assert metrics.total_ms.p50 == 205.0
        # p95 (idx = 3 * 0.95 = 2.85 -> 280*0.15 + 520*0.85 = 42 + 442 = 484.0)
        assert metrics.total_ms.p95 == 484.0

    def test_empty_workspace_metrics_works(self, client, trace_env):
        """Calling /metrics on a workspace with zero traces returns 0s without crashing."""
        ws_id = trace_env["ws_b"].id
        headers = {"Authorization": f"Bearer {trace_env['token_b']}"}

        res = client.get(f"/api/workspaces/{ws_id}/metrics", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["request_count"] == 0
        assert data["abstain_rate"] == 0.0
        assert data["error_rate"] == 0.0
        assert data["total_ms"]["p50"] == 0.0
        assert data["total_ms"]["p95"] == 0.0

    def test_workspace_isolation(self, client, trace_env):
        """Traces and metrics from Workspace A never appear in Workspace B."""
        ws_a = trace_env["ws_a"].id
        ws_b = trace_env["ws_b"].id
        headers_a = {"Authorization": f"Bearer {trace_env['token_a']}"}
        headers_b = {"Authorization": f"Bearer {trace_env['token_b']}"}

        # Make request in Workspace A
        client.post(f"/api/workspaces/{ws_a}/ask", headers=headers_a, json={"question": "q for A"})

        # Workspace A has 1 trace
        traces_a = client.get(f"/api/workspaces/{ws_a}/traces", headers=headers_a).json()
        assert len(traces_a) == 1

        # Workspace B has 0 traces
        traces_b = client.get(f"/api/workspaces/{ws_b}/traces", headers=headers_b).json()
        assert len(traces_b) == 0

        # Workspace B metrics reflect 0 requests
        metrics_b = client.get(f"/api/workspaces/{ws_b}/metrics", headers=headers_b).json()
        assert metrics_b["request_count"] == 0

    def test_non_member_cannot_access_traces_or_metrics(self, client, trace_env):
        """User C (not in workspace) gets 404 for traces and metrics."""
        ws_id = trace_env["ws_a"].id
        headers_c = {"Authorization": f"Bearer {trace_env['token_c']}"}

        assert client.get(f"/api/workspaces/{ws_id}/traces", headers=headers_c).status_code == 404
        assert client.get(f"/api/workspaces/{ws_id}/metrics", headers=headers_c).status_code == 404
