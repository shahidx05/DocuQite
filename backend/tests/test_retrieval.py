"""
tests/test_retrieval.py — Phase 4A tests for retrieval_service and search endpoint.

Always uses rag_chunks_test collection (never the dev collection).
Always uses ragdb_test database (never ragdb).

Design:
- Module-scoped fixture ensures the test collection exists before any test runs.
- Function-scoped fixture patches QDRANT_COLLECTION and both embedding functions
  with fast fakes so tests are deterministic and don't load ONNX models.
- Seed helpers upsert real (fake) vectors; cleanup deletes them afterward.
- HTTP tests use FastAPI TestClient with a patched get_current_user dependency.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from qdrant_client.http import models as qmodels

import app.services.embedding_service as emb_mod
from app.core.config import settings
from app.main import app
from app.services import retrieval_service
from app.services.vector_service import (
    delete_by_workspace,
    ensure_collection,
    get_qdrant_client,
    upsert_chunks,
)

TEST_COLLECTION = "rag_chunks_test"

# ── Fake embedding functions ───────────────────────────────────────────────────

FAKE_DIM = 384

def _fake_dense(text: str) -> list[float]:
    """Deterministic fake dense vector (all 0.1)."""
    return [0.1] * FAKE_DIM


def _fake_sparse(text: str) -> dict:
    """Deterministic fake sparse vector."""
    return {"indices": [0, 1, 2], "values": [0.5, 0.3, 0.2]}


# ── Fake chunk ORM objects ─────────────────────────────────────────────────────

class _FakeChunk:
    """Minimal stand-in for the Chunk ORM model (only fields upsert_chunks needs)."""
    def __init__(self, workspace_id, document_id=None, page_number=1,
                 section_title="Section A", text="sample text", chunk_index=0):
        self.id = uuid.uuid4()
        self.document_id = document_id or uuid.uuid4()
        self.workspace_id = workspace_id
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.section_title = section_title
        self.text = text


# ── Module-scoped: ensure the test collection exists once ─────────────────────

@pytest.fixture(scope="module", autouse=True)
def ensure_test_collection():
    ensure_collection(TEST_COLLECTION)


# ── Function-scoped: patch settings + embedding functions, cleanup workspace ──

@pytest.fixture()
def patched_retrieval(monkeypatch):
    """
    Patch QDRANT_COLLECTION and both embedding functions.
    Yields a dict with helpers; cleans up all test workspaces afterward.
    """
    seeded_ws_ids = []

    monkeypatch.setattr(settings, "QDRANT_COLLECTION", TEST_COLLECTION)
    monkeypatch.setattr(emb_mod, "embed_query", _fake_dense)
    monkeypatch.setattr(emb_mod, "sparse_query", _fake_sparse)
    # Also patch the references inside retrieval_service (it imports the functions)
    monkeypatch.setattr("app.services.retrieval_service.embedding_service.embed_query", _fake_dense)
    monkeypatch.setattr("app.services.retrieval_service.embedding_service.sparse_query", _fake_sparse)

    def seed_workspace(n=3, workspace_id=None, document_id=None,
                       texts=None, section_titles=None, sparse_vecs=None):
        """Upsert n fake chunks; return (workspace_id, document_id, chunks)."""
        ws_id = workspace_id or uuid.uuid4()
        doc_id = document_id or uuid.uuid4()
        chunks = []
        for i in range(n):
            text = texts[i] if texts else f"chunk text number {i}"
            sec = section_titles[i] if section_titles else "Section"
            chunks.append(_FakeChunk(ws_id, doc_id, page_number=i + 1,
                                     section_title=sec, text=text, chunk_index=i))

        dense_vecs = [[0.1] * FAKE_DIM for _ in chunks]
        if sparse_vecs is None:
            sparse_vecs = [{"indices": [i, i + 1], "values": [0.5, 0.5]} for i in range(n)]

        upsert_chunks(
            chunks_db=chunks,
            document_name="test_doc.pdf",
            dense_vecs=dense_vecs,
            sparse_vecs=sparse_vecs,
            collection_name=TEST_COLLECTION,
        )
        seeded_ws_ids.append(ws_id)
        return ws_id, doc_id, chunks

    yield {"seed": seed_workspace, "collection": TEST_COLLECTION}

    # Cleanup: delete all seeded workspaces
    for ws_id in seeded_ws_ids:
        delete_by_workspace(ws_id, collection_name=TEST_COLLECTION)


# ── Fake user for HTTP tests ───────────────────────────────────────────────────

@pytest.fixture()
def http_client(monkeypatch):
    """
    TestClient with QDRANT_COLLECTION patched and embedding fakes installed.
    Does NOT override auth — individual tests inject their own auth overrides.
    """
    monkeypatch.setattr(settings, "QDRANT_COLLECTION", TEST_COLLECTION)
    monkeypatch.setattr("app.services.retrieval_service.embedding_service.embed_query", _fake_dense)
    monkeypatch.setattr("app.services.retrieval_service.embedding_service.sparse_query", _fake_sparse)
    return TestClient(app, raise_server_exceptions=True)


def _mock_member(workspace_id: uuid.UUID):
    """Return a fake (workspace, member) pair for the given workspace_id."""
    ws = MagicMock()
    ws.id = workspace_id
    member = MagicMock()
    member.role = "member"
    return ws, member


# ═══════════════════════════════════════════════════════════════════════════════
# Retrieval service — unit tests (call retrieve() directly)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetrieveHybrid:
    def test_hybrid_returns_results(self, patched_retrieval):
        ws_id, _, _ = patched_retrieval["seed"](n=3)
        results = retrieval_service.retrieve(ws_id, "test query", mode="hybrid", top_k=5,
                                              collection_name=TEST_COLLECTION)
        assert len(results) >= 1
        assert all(r.mode == "hybrid" for r in results)

    def test_dense_returns_results(self, patched_retrieval):
        ws_id, _, _ = patched_retrieval["seed"](n=3)
        results = retrieval_service.retrieve(ws_id, "test query", mode="dense", top_k=5,
                                              collection_name=TEST_COLLECTION)
        assert len(results) >= 1
        assert all(r.mode == "dense" for r in results)

    def test_sparse_returns_results(self, patched_retrieval):
        ws_id, _, _ = patched_retrieval["seed"](n=3)
        results = retrieval_service.retrieve(ws_id, "test query", mode="sparse", top_k=5,
                                              collection_name=TEST_COLLECTION)
        assert len(results) >= 1
        assert all(r.mode == "sparse" for r in results)


class TestSparseKeywordRanking:
    def test_sparse_exact_keyword_ranks_first(self, patched_retrieval):
        """
        Seed two chunks with clearly different sparse vectors so the
        'activation softcomputing' chunk scores higher in sparse mode
        than a generic 'other topic' chunk.
        """
        ws_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        # Target chunk — sparse vector has high weight on index 42 (simulating keyword hit)
        target_chunk = _FakeChunk(ws_id, doc_id, text="activation softcomputing techniques",
                                  section_title="Core Topic", chunk_index=0)
        # Noise chunk — sparse vector has zero overlap with target's indices
        noise_chunk = _FakeChunk(ws_id, doc_id, text="unrelated generic filler content",
                                 section_title="Noise", chunk_index=1)

        # Give target a strong distinct sparse vector; give noise a weak one
        dense_vecs = [[0.1] * FAKE_DIM, [0.1] * FAKE_DIM]
        sparse_vecs = [
            {"indices": [42, 43], "values": [1.0, 0.9]},   # target — matches query below
            {"indices": [99, 100], "values": [0.01, 0.01]}, # noise — no match
        ]
        upsert_chunks(
            chunks_db=[target_chunk, noise_chunk],
            document_name="test_doc.pdf",
            dense_vecs=dense_vecs,
            sparse_vecs=sparse_vecs,
            collection_name=TEST_COLLECTION,
        )

        # Query with a fake sparse vector that matches the target's indices
        def _query_sparse_matching(text: str) -> dict:
            return {"indices": [42, 43], "values": [1.0, 0.9]}

        import app.services.retrieval_service as rs_mod
        original = rs_mod.embedding_service.sparse_query
        rs_mod.embedding_service.sparse_query = _query_sparse_matching
        try:
            results = retrieval_service.retrieve(ws_id, "activation softcomputing",
                                                  mode="sparse", top_k=5,
                                                  collection_name=TEST_COLLECTION)
            assert len(results) >= 1
            assert results[0].chunk_id == target_chunk.id
        finally:
            rs_mod.embedding_service.sparse_query = original
            delete_by_workspace(ws_id, collection_name=TEST_COLLECTION)


class TestWorkspaceIsolation:
    """Chunks from workspace B must never appear in workspace A results."""

    def _run_isolation(self, patched_retrieval, mode):
        ws_a_id, _, chunks_a = patched_retrieval["seed"](n=2)
        ws_b_id, _, _ = patched_retrieval["seed"](n=2)

        a_chunk_ids = {c.id for c in chunks_a}

        results = retrieval_service.retrieve(ws_a_id, "test query", mode=mode, top_k=10,
                                              collection_name=TEST_COLLECTION)

        returned_ws_ids = {r.chunk_id for r in results}
        # No result should belong to workspace B
        b_leaked = [r for r in results if r.chunk_id not in a_chunk_ids]
        assert b_leaked == [], f"Workspace B chunks leaked into workspace A results ({mode})"

    def test_workspace_isolation_dense(self, patched_retrieval):
        self._run_isolation(patched_retrieval, "dense")

    def test_workspace_isolation_sparse(self, patched_retrieval):
        self._run_isolation(patched_retrieval, "sparse")

    def test_workspace_isolation_hybrid(self, patched_retrieval):
        self._run_isolation(patched_retrieval, "hybrid")


class TestTopKRespected:
    def test_top_k_respected(self, patched_retrieval):
        ws_id, _, _ = patched_retrieval["seed"](n=10)
        for mode in ("dense", "sparse", "hybrid"):
            results = retrieval_service.retrieve(ws_id, "query", mode=mode, top_k=3,
                                                  collection_name=TEST_COLLECTION)
            assert len(results) <= 3, f"top_k=3 violated in {mode} mode"


# ═══════════════════════════════════════════════════════════════════════════════
# Search API — HTTP tests (via TestClient)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearchAPI:
    def test_non_member_gets_404(self, http_client):
        """Non-member (or non-existent workspace) must return 404."""
        from fastapi import HTTPException
        from app.api import deps

        def _not_a_member(workspace_id: uuid.UUID = None):
            raise HTTPException(status_code=404, detail="Workspace not found.")

        app.dependency_overrides[deps.require_workspace_member] = _not_a_member
        try:
            resp = http_client.get(f"/api/workspaces/{uuid.uuid4()}/search?q=hello")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(deps.require_workspace_member, None)

    def test_empty_query_gets_422(self, http_client):
        """Empty q violates min_length=1 and must return 422."""
        ws_id = uuid.uuid4()
        from app.api import deps

        def _ok(workspace_id: uuid.UUID = None):
            return _mock_member(ws_id)

        app.dependency_overrides[deps.require_workspace_member] = _ok
        try:
            # q="" violates min_length=1
            resp = http_client.get(f"/api/workspaces/{ws_id}/search?q=")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(deps.require_workspace_member, None)

    def test_invalid_mode_gets_422(self, http_client):
        """mode not in {dense,sparse,hybrid} must return 422."""
        ws_id = uuid.uuid4()
        from app.api import deps

        def _ok(workspace_id: uuid.UUID = None):
            return _mock_member(ws_id)

        app.dependency_overrides[deps.require_workspace_member] = _ok
        try:
            resp = http_client.get(f"/api/workspaces/{ws_id}/search?q=hello&mode=bad_mode")
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(deps.require_workspace_member, None)

    def test_valid_search_returns_200(self, http_client, patched_retrieval):
        """A valid request from a member must return 200 with the expected shape."""
        ws_id, _, _ = patched_retrieval["seed"](n=3)
        from app.api import deps

        def _ok(workspace_id: uuid.UUID = None):
            return _mock_member(ws_id)

        app.dependency_overrides[deps.require_workspace_member] = _ok
        try:
            resp = http_client.get(
                f"/api/workspaces/{ws_id}/search",
                params={"q": "test query", "mode": "hybrid", "top_k": 5},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["query"] == "test query"
            assert body["mode"] == "hybrid"
            assert "took_ms" in body
            assert isinstance(body["results"], list)
        finally:
            app.dependency_overrides.pop(deps.require_workspace_member, None)
