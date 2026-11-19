"""
services/vector_service.py — Qdrant collection management and vector operations.

ONE shared collection (QDRANT_COLLECTION) with:
  - Named dense vector  "dense"  : EMBEDDING_DIM dims, cosine distance
  - Named sparse vector "sparse" : BM25, IDF modifier

Payload indexes on workspace_id and document_id enable efficient filtered search.
Point id = chunk UUID (string form).

Payload stored per point:
    chunk_id, document_id, workspace_id, document_name,
    page_number, section_title, chunk_index, text
"""

import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

logger = logging.getLogger(__name__)

# Named vector keys — single source of truth used here and in search.
DENSE_VECTOR_NAME  = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_qdrant_client() -> QdrantClient:
    """Return a configured Qdrant client (no network call yet)."""
    return QdrantClient(url=settings.QDRANT_URL)


def check_qdrant() -> bool:
    """Return True if Qdrant is reachable, False otherwise."""
    try:
        client = get_qdrant_client()
        client.get_collections()
        return True
    except Exception as exc:
        logger.warning("Qdrant ping failed: %s", exc)
        return False


def ensure_collection(collection_name: str | None = None) -> None:
    """
    Create the collection if it does not already exist. Idempotent.
    Uses the named-vectors API so both dense and sparse live in one collection.
    """
    name = collection_name or settings.QDRANT_COLLECTION
    client = get_qdrant_client()

    existing = {c.name for c in client.get_collections().collections}
    if name in existing:
        logger.debug("Collection '%s' already exists — skipping create.", name)
        return

    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR_NAME: qmodels.VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=qmodels.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(
                modifier=qmodels.Modifier.IDF,
            ),
        },
    )
    logger.info("Created collection '%s'.", name)

    # Create payload indexes so filtered search is fast.
    for field in ("workspace_id", "document_id"):
        client.create_payload_index(
            collection_name=name,
            field_name=field,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )
    logger.info("Payload indexes created on workspace_id, document_id.")


def upsert_chunks(
    chunks_db: list,          # list of Chunk ORM objects
    document_name: str,
    dense_vecs: list[list[float]],
    sparse_vecs: list[dict],
    collection_name: str | None = None,
) -> None:
    """
    Upsert one Qdrant point per chunk.

    chunk_db rows must have: id, document_id, workspace_id, chunk_index,
    page_number, section_title, text.
    dense_vecs[i] and sparse_vecs[i] correspond to chunks_db[i].
    """
    name = collection_name or settings.QDRANT_COLLECTION
    client = get_qdrant_client()

    points: list[qmodels.PointStruct] = []
    for chunk, dvec, svec in zip(chunks_db, dense_vecs, sparse_vecs):
        points.append(
            qmodels.PointStruct(
                id=str(chunk.id),          # UUID as string
                vector={
                    DENSE_VECTOR_NAME: dvec,
                    SPARSE_VECTOR_NAME: qmodels.SparseVector(
                        indices=svec["indices"],
                        values=svec["values"],
                    ),
                },
                payload={
                    "chunk_id":      str(chunk.id),
                    "document_id":   str(chunk.document_id),
                    "workspace_id":  str(chunk.workspace_id),
                    "document_name": document_name,
                    "page_number":   chunk.page_number,
                    "section_title": chunk.section_title,
                    "chunk_index":   chunk.chunk_index,
                    "text":          chunk.text,
                },
            )
        )

    # upsert handles both inserts and updates (idempotent on retry).
    client.upsert(collection_name=name, points=points, wait=True)
    logger.info("Upserted %d points into '%s'.", len(points), name)


def delete_by_document(
    document_id: uuid.UUID,
    collection_name: str | None = None,
) -> None:
    """Delete all Qdrant points whose payload.document_id == document_id."""
    name = collection_name or settings.QDRANT_COLLECTION
    client = get_qdrant_client()
    client.delete(
        collection_name=name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="document_id",
                        match=qmodels.MatchValue(value=str(document_id)),
                    )
                ]
            )
        ),
        wait=True,
    )
    logger.info("Deleted vectors for document_id=%s from '%s'.", document_id, name)


def delete_by_workspace(
    workspace_id: uuid.UUID,
    collection_name: str | None = None,
) -> None:
    """Delete all Qdrant points whose payload.workspace_id == workspace_id."""
    name = collection_name or settings.QDRANT_COLLECTION
    client = get_qdrant_client()
    client.delete(
        collection_name=name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="workspace_id",
                        match=qmodels.MatchValue(value=str(workspace_id)),
                    )
                ]
            )
        ),
        wait=True,
    )
    logger.info("Deleted vectors for workspace_id=%s from '%s'.", workspace_id, name)


def count_by_document(
    document_id: uuid.UUID,
    collection_name: str | None = None,
) -> int:
    """Return the number of Qdrant points for a document (used in tests)."""
    name = collection_name or settings.QDRANT_COLLECTION
    client = get_qdrant_client()
    result = client.count(
        collection_name=name,
        count_filter=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="document_id",
                    match=qmodels.MatchValue(value=str(document_id)),
                )
            ]
        ),
        exact=True,
    )
    return result.count
