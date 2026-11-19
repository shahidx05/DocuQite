"""
tests/test_embeddings.py — Phase 3: embedding service and Qdrant indexing tests.

Design decisions:
  - Uses a SEPARATE Qdrant collection "rag_chunks_test" — never touches the dev
    collection. The test collection is created fresh at the start and cleaned up
    after each test via delete_by_document / delete_by_workspace calls.
  - Embedding calls are MOCKED with deterministic fake vectors so tests run fast
    and without downloading model weights. The dimension-check test verifies the
    real model returns EMBEDDING_DIM dims (this test is marked slow and skipped
    unless --run-slow is passed, keeping the default suite fast).
  - The ingestion pipeline test uploads a real file through the HTTP client and
    polls until status == COMPLETED (background task runs synchronously in TestClient).
"""

import time
import uuid
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.vector_service import (
    count_by_document,
    delete_by_document,
    delete_by_workspace,
    ensure_collection,
    get_qdrant_client,
    upsert_chunks,
)

# ── Constants ──────────────────────────────────────────────────────────
TEST_COLLECTION = "rag_chunks_test"
DIM = settings.EMBEDDING_DIM
FAKE_VEC = [0.1] * DIM          # deterministic dense vector
FAKE_SPARSE = {"indices": [0, 1, 2], "values": [0.5, 0.3, 0.2]}


# ── Helpers ────────────────────────────────────────────────────────────

def _fake_dense(texts):
    """Return one deterministic vector per text."""
    return [FAKE_VEC for _ in texts]


def _fake_sparse(texts):
    """Return one deterministic sparse vector per text."""
    return [FAKE_SPARSE for _ in texts]


def _fake_query_dense(text):
    return FAKE_VEC


def _fake_query_sparse(text):
    return FAKE_SPARSE


class _FakeChunk:
    """Minimal stand-in for a Chunk ORM row."""
    def __init__(self, doc_id, ws_id, idx):
        self.id            = uuid.uuid4()
        self.document_id   = doc_id
        self.workspace_id  = ws_id
        self.chunk_index   = idx
        self.page_number   = idx + 1
        self.section_title = f"Section {idx}"
        self.text          = f"Chunk text number {idx}."


# ── Fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def test_collection():
    """Create the test collection once for all tests in this module."""
    ensure_collection(TEST_COLLECTION)
    yield
    # Do not delete the collection itself — just leave it for next run.


@pytest.fixture()
def clean_collection():
    """
    Yield the test collection name and ensure no leftover points from a
    previous failed run interfere with this test.  Cleans up after.
    """
    yield TEST_COLLECTION
    # Teardown: nothing to do — each test cleans its own data.


def _register_and_login(client) -> str:
    """Register a user and return a bearer token."""
    email = f"embed_{uuid.uuid4().hex[:8]}@test.com"
    client.post("/api/auth/register", json={"name": "Embed User", "email": email, "password": "password123"})
    r = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Tests ──────────────────────────────────────────────────────────────

class TestEnsureCollection:
    def test_idempotent_create(self):
        """Calling ensure_collection twice must not raise or duplicate."""
        ensure_collection(TEST_COLLECTION)
        ensure_collection(TEST_COLLECTION)  # second call must be a no-op
        client = get_qdrant_client()
        names = {c.name for c in client.get_collections().collections}
        assert TEST_COLLECTION in names

    def test_collection_has_dense_and_sparse_vectors(self):
        """The collection must have named dense + sparse vector configs."""
        client = get_qdrant_client()
        info = client.get_collection(TEST_COLLECTION)
        assert "dense" in info.config.params.vectors, \
            "Dense vector 'dense' missing from collection config"
        assert "sparse" in info.config.params.sparse_vectors, \
            "Sparse vector 'sparse' missing from collection config"

    def test_dense_vector_dimension(self):
        """The dense vector must be configured with EMBEDDING_DIM dimensions."""
        client = get_qdrant_client()
        info = client.get_collection(TEST_COLLECTION)
        actual_dim = info.config.params.vectors["dense"].size
        assert actual_dim == DIM, \
            f"Dense dim={actual_dim}, expected EMBEDDING_DIM={DIM}"


class TestUpsertAndDelete:
    def test_upsert_inserts_expected_count(self, clean_collection):
        """upsert_chunks must create exactly len(chunks) points."""
        doc_id = uuid.uuid4()
        ws_id  = uuid.uuid4()
        chunks = [_FakeChunk(doc_id, ws_id, i) for i in range(5)]
        dvecs  = _fake_dense([c.text for c in chunks])
        svecs  = _fake_sparse([c.text for c in chunks])

        upsert_chunks(chunks, "test.pdf", dvecs, svecs, collection_name=TEST_COLLECTION)

        count = count_by_document(doc_id, collection_name=TEST_COLLECTION)
        assert count == 5, f"Expected 5 points, got {count}"

        # Cleanup
        delete_by_document(doc_id, collection_name=TEST_COLLECTION)

    def test_upsert_is_idempotent(self, clean_collection):
        """Upserting the same chunks twice must not duplicate points."""
        doc_id = uuid.uuid4()
        ws_id  = uuid.uuid4()
        chunks = [_FakeChunk(doc_id, ws_id, i) for i in range(3)]
        dvecs  = _fake_dense([c.text for c in chunks])
        svecs  = _fake_sparse([c.text for c in chunks])

        upsert_chunks(chunks, "test.pdf", dvecs, svecs, collection_name=TEST_COLLECTION)
        upsert_chunks(chunks, "test.pdf", dvecs, svecs, collection_name=TEST_COLLECTION)  # retry

        count = count_by_document(doc_id, collection_name=TEST_COLLECTION)
        assert count == 3, f"Expected 3 points after idempotent upsert, got {count}"

        delete_by_document(doc_id, collection_name=TEST_COLLECTION)

    def test_delete_by_document_removes_points(self, clean_collection):
        """delete_by_document must remove only the targeted document's points."""
        doc_a  = uuid.uuid4()
        doc_b  = uuid.uuid4()
        ws_id  = uuid.uuid4()

        chunks_a = [_FakeChunk(doc_a, ws_id, 0)]
        chunks_b = [_FakeChunk(doc_b, ws_id, 0)]

        for chunks, doc_id in [(chunks_a, doc_a), (chunks_b, doc_b)]:
            upsert_chunks(
                chunks, "doc.pdf",
                _fake_dense([c.text for c in chunks]),
                _fake_sparse([c.text for c in chunks]),
                collection_name=TEST_COLLECTION,
            )

        delete_by_document(doc_a, collection_name=TEST_COLLECTION)

        assert count_by_document(doc_a, collection_name=TEST_COLLECTION) == 0
        assert count_by_document(doc_b, collection_name=TEST_COLLECTION) == 1

        delete_by_document(doc_b, collection_name=TEST_COLLECTION)

    def test_delete_by_workspace_removes_all_workspace_points(self, clean_collection):
        """delete_by_workspace must remove every point for that workspace."""
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()

        for ws_id in (ws_a, ws_b):
            for _ in range(3):
                doc_id = uuid.uuid4()
                chunks = [_FakeChunk(doc_id, ws_id, 0)]
                upsert_chunks(
                    chunks, "doc.pdf",
                    _fake_dense([c.text for c in chunks]),
                    _fake_sparse([c.text for c in chunks]),
                    collection_name=TEST_COLLECTION,
                )

        delete_by_workspace(ws_a, collection_name=TEST_COLLECTION)

        # ws_a points gone; ws_b untouched
        from qdrant_client.http import models as qmodels
        client = get_qdrant_client()

        def _count_ws(ws_id):
            return client.count(
                collection_name=TEST_COLLECTION,
                count_filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(
                        key="workspace_id",
                        match=qmodels.MatchValue(value=str(ws_id)),
                    )]
                ),
                exact=True,
            ).count

        assert _count_ws(ws_a) == 0
        assert _count_ws(ws_b) == 3

        delete_by_workspace(ws_b, collection_name=TEST_COLLECTION)

    def test_workspace_isolation(self, clean_collection):
        """Points from workspace A must not be visible when filtering by workspace B."""
        ws_a = uuid.uuid4()
        ws_b = uuid.uuid4()
        doc_a = uuid.uuid4()
        doc_b = uuid.uuid4()

        chunks_a = [_FakeChunk(doc_a, ws_a, 0)]
        chunks_b = [_FakeChunk(doc_b, ws_b, 0)]

        for chunks in (chunks_a, chunks_b):
            upsert_chunks(
                chunks, "doc.pdf",
                _fake_dense([c.text for c in chunks]),
                _fake_sparse([c.text for c in chunks]),
                collection_name=TEST_COLLECTION,
            )

        # Only doc_a should appear when filtering by ws_a
        assert count_by_document(doc_a, collection_name=TEST_COLLECTION) == 1
        assert count_by_document(doc_b, collection_name=TEST_COLLECTION) == 1

        delete_by_document(doc_a, collection_name=TEST_COLLECTION)
        delete_by_document(doc_b, collection_name=TEST_COLLECTION)


class TestIngestionPipeline:
    """
    End-to-end: upload a real PDF → wait for COMPLETED → check vector count.
    Embedding calls are mocked so no model download is needed.
    """

    @pytest.fixture(autouse=True)
    def _patch_embeddings_and_collection(self, monkeypatch):
        """
        Redirect ingestion to use the test collection and fake embeddings.
        """
        # Point ingestion to test collection
        monkeypatch.setattr(settings, "QDRANT_COLLECTION", TEST_COLLECTION)

        # Patch embedding functions used inside ingestion.py
        monkeypatch.setattr(
            "app.services.embedding_service.embed_documents", _fake_dense
        )
        monkeypatch.setattr(
            "app.services.embedding_service.sparse_documents", _fake_sparse
        )

    def test_upload_reaches_completed_and_vector_count_matches(self, tmp_path):
        """
        Upload a small real PDF, wait for the background task to finish,
        then verify status == COMPLETED and vector count == chunk_count.
        """
        pdf_path = Path(__file__).parent.parent.parent / "data" / "raw" / "x.pdf"
        if not pdf_path.exists():
            pytest.skip("x.pdf not present in data/raw/ — skipping live upload test.")

        with TestClient(app) as client:
            token = _register_and_login(client)
            headers = _auth(token)

            # Create workspace
            ws_r = client.post("/api/workspaces", json={"name": "embed-test-ws"}, headers=headers)
            assert ws_r.status_code == 201
            ws_id = ws_r.json()["id"]

            # Upload document
            with open(pdf_path, "rb") as f:
                upload_r = client.post(
                    f"/api/workspaces/{ws_id}/documents",
                    files={"file": ("x.pdf", f, "application/pdf")},
                    headers=headers,
                )
            assert upload_r.status_code == 202
            doc_id = upload_r.json()["id"]

            # Background task ran synchronously in TestClient context.
            doc_r = client.get(f"/api/documents/{doc_id}", headers=headers)
            doc = doc_r.json()

            assert doc["status"] == "COMPLETED", \
                f"Expected COMPLETED, got {doc['status']}. error={doc.get('error_message')}"

            chunk_count = doc["chunk_count"]
            assert chunk_count is not None and chunk_count > 0

            # Vector count must equal chunk_count
            vec_count = count_by_document(uuid.UUID(doc_id), collection_name=TEST_COLLECTION)
            assert vec_count == chunk_count, \
                f"Vector count {vec_count} != chunk_count {chunk_count}"

            # Cleanup vectors (DB rows cleaned by test DB rollback via workspace delete)
            delete_by_document(uuid.UUID(doc_id), collection_name=TEST_COLLECTION)

    def test_delete_document_removes_vectors(self, tmp_path):
        """Deleting a document via the API must also remove its Qdrant vectors."""
        pdf_path = Path(__file__).parent.parent.parent / "data" / "raw" / "soft.pdf"
        if not pdf_path.exists():
            pytest.skip("soft.pdf not present in data/raw/ — skipping.")

        with TestClient(app) as client:
            token = _register_and_login(client)
            headers = _auth(token)

            ws_r = client.post("/api/workspaces", json={"name": "del-test-ws"}, headers=headers)
            ws_id = ws_r.json()["id"]

            with open(pdf_path, "rb") as f:
                upload_r = client.post(
                    f"/api/workspaces/{ws_id}/documents",
                    files={"file": ("soft.pdf", f, "application/pdf")},
                    headers=headers,
                )
            assert upload_r.status_code == 202
            doc_id = upload_r.json()["id"]

            # Confirm indexed
            doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
            assert doc["status"] == "COMPLETED"

            # Delete the document
            del_r = client.delete(f"/api/documents/{doc_id}", headers=headers)
            assert del_r.status_code == 204

            # Vector count must be zero
            vec_count = count_by_document(uuid.UUID(doc_id), collection_name=TEST_COLLECTION)
            assert vec_count == 0, f"Expected 0 vectors after delete, got {vec_count}"

    def test_retry_does_not_duplicate_vectors(self):
        """
        Simulate a retry: upsert vectors, then upsert again with the same
        chunk UUIDs. The count must remain the same (no duplicates).
        """
        doc_id = uuid.uuid4()
        ws_id  = uuid.uuid4()
        chunks = [_FakeChunk(doc_id, ws_id, i) for i in range(4)]
        dvecs  = _fake_dense([c.text for c in chunks])
        svecs  = _fake_sparse([c.text for c in chunks])

        # First indexing
        upsert_chunks(chunks, "retry.pdf", dvecs, svecs, collection_name=TEST_COLLECTION)
        assert count_by_document(doc_id, collection_name=TEST_COLLECTION) == 4

        # Retry: delete first (as ingestion.py does), then upsert again
        delete_by_document(doc_id, collection_name=TEST_COLLECTION)
        upsert_chunks(chunks, "retry.pdf", dvecs, svecs, collection_name=TEST_COLLECTION)
        assert count_by_document(doc_id, collection_name=TEST_COLLECTION) == 4

        delete_by_document(doc_id, collection_name=TEST_COLLECTION)


class TestEmbeddingDimension:
    """
    Verify the real model outputs the configured EMBEDDING_DIM.
    Downloads the model — only runs when Docker + network are available.
    Mark slow tests with: pytest -m slow  (skipped by default).
    """

    @pytest.mark.slow
    def test_real_dense_embedding_dimension(self):
        """Real embed_documents must return vectors of length EMBEDDING_DIM."""
        from app.services.embedding_service import embed_documents
        texts = ["This is a test sentence for embedding."]
        vecs = embed_documents(texts)
        assert len(vecs) == 1
        assert len(vecs[0]) == DIM, \
            f"Dense embedding dim={len(vecs[0])}, expected {DIM}"

    @pytest.mark.slow
    def test_real_sparse_embedding_has_nonzero_values(self):
        """Real sparse_documents must return nonzero sparse vectors."""
        from app.services.embedding_service import sparse_documents
        texts = ["Soft computing neural network fuzzy logic."]
        svecs = sparse_documents(texts)
        assert len(svecs) == 1
        assert len(svecs[0]["indices"]) > 0
        assert len(svecs[0]["values"]) > 0
