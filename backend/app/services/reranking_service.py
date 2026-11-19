"""
services/reranking_service.py — Cross-encoder reranking using fastembed.

Lazy-loads TextCrossEncoder once on first use (singleton pattern).
Function:
    rerank(query, results, top_n) -> list[RetrievalResult]
Scores query-passage pairs, preserves original_rank (1-based), records rerank_score,
and returns results sorted in descending order of rerank_score.
"""

import logging
from typing import Optional

from app.core.config import settings
from app.schemas.search import RetrievalResult

logger = logging.getLogger(__name__)

# Module-level singleton — None until first use.
_cross_encoder = None


def _get_cross_encoder():
    """Return the TextCrossEncoder model, loading it on first call."""
    global _cross_encoder
    if _cross_encoder is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        model_name = settings.RERANKER_MODEL
        # Normalize legacy HuggingFace repo identifier to fastembed supported name if needed
        if model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2":
            model_name = "Xenova/ms-marco-MiniLM-L-6-v2"

        logger.info("Loading cross-encoder model: %s", model_name)
        _cross_encoder = TextCrossEncoder(model_name=model_name)
        logger.info("Cross-encoder model ready.")
    return _cross_encoder


def rerank(
    query: str,
    results: list[RetrievalResult],
    top_n: Optional[int] = None,
) -> list[RetrievalResult]:
    """
    Rerank a list of RetrievalResult candidates using the cross-encoder model.

    Args:
        query:   Search query string.
        results: Candidate RetrievalResult objects from initial retrieval.
        top_n:   Maximum number of reranked results to return (defaults to settings.RERANK_TOP_N).

    Returns:
        New list of RetrievalResult sorted by cross-encoder score descending,
        with original_rank (1-based) and rerank_score populated.
    """
    if not results:
        return []

    if top_n is None:
        top_n = settings.RERANK_TOP_N

    # Extract passage texts from candidate results.
    documents = [r.text for r in results]

    model = _get_cross_encoder()
    raw_scores = list(model.rerank(query=query, documents=documents))

    # Build updated results preserving original_rank (1-based index)
    reranked: list[RetrievalResult] = []
    for idx, (res, score) in enumerate(zip(results, raw_scores)):
        # Create a copy or update fields
        updated = res.model_copy()
        updated.original_rank = idx + 1
        updated.rerank_score = float(score)
        reranked.append(updated)

    # Sort descending by cross-encoder score
    reranked.sort(key=lambda r: (r.rerank_score if r.rerank_score is not None else float("-inf")), reverse=True)

    return reranked[:top_n]
