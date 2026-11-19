"""
services/embedding_service.py — Lazy-loaded fastembed models.

Models are loaded once on first use (singleton pattern) so the heavy
ONNX runtime is not initialised until an embedding is actually needed.

Embedding text format (for both dense and sparse):
    "{document_name} | {section_title}\\n{chunk text}"
Stored chunk text is NEVER modified — only the input to the model differs.

Dense model  : BAAI/bge-small-en-v1.5  (384-dim, cosine)
Sparse model : Qdrant/bm25             (BM25 IDF)
"""

import logging
from typing import Generator

from app.core.config import settings

logger = logging.getLogger(__name__)

# Module-level singletons — None until first use.
_dense_model = None
_sparse_model = None


def _get_dense():
    """Return the TextEmbedding model, loading it on first call."""
    global _dense_model
    if _dense_model is None:
        from fastembed import TextEmbedding
        logger.info("Loading dense model: %s", settings.EMBEDDING_MODEL)
        _dense_model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
        logger.info("Dense model ready.")
    return _dense_model


def _get_sparse():
    """Return the SparseTextEmbedding model, loading it on first call."""
    global _sparse_model
    if _sparse_model is None:
        from fastembed import SparseTextEmbedding
        logger.info("Loading sparse model: %s", settings.SPARSE_MODEL)
        _sparse_model = SparseTextEmbedding(model_name=settings.SPARSE_MODEL)
        logger.info("Sparse model ready.")
    return _sparse_model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """
    Embed a batch of passage texts with the dense bi-encoder.
    Uses the passage variant (prefix added internally by bge models).
    Returns a list of float vectors, one per input text.
    """
    model = _get_dense()
    batch = settings.EMBED_BATCH_SIZE
    results: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        # embed() returns a generator; passage_embed() uses the passage prefix.
        for vec in model.passage_embed(chunk):
            results.append(vec.tolist())
    return results


def embed_query(text: str) -> list[float]:
    """
    Embed a single query text with the dense bi-encoder.
    Uses the query variant (different prefix from passage_embed).
    """
    model = _get_dense()
    # query_embed returns a generator; take the first (and only) result.
    for vec in model.query_embed([text]):
        return vec.tolist()
    raise RuntimeError("embed_query returned no vectors")  # should never happen


def sparse_documents(texts: list[str]) -> list[dict]:
    """
    Compute BM25 sparse vectors for a batch of passage texts.
    Returns a list of dicts with keys "indices" and "values".
    """
    model = _get_sparse()
    batch = settings.EMBED_BATCH_SIZE
    results: list[dict] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        for sv in model.embed(chunk):
            results.append({"indices": sv.indices.tolist(), "values": sv.values.tolist()})
    return results


def sparse_query(text: str) -> dict:
    """
    Compute BM25 sparse vector for a single query string.
    Returns a dict with keys "indices" and "values".
    """
    model = _get_sparse()
    for sv in model.query_embed([text]):
        return {"indices": sv.indices.tolist(), "values": sv.values.tolist()}
    raise RuntimeError("sparse_query returned no vectors")
