"""
services/retrieval_service.py — Hybrid retrieval from Qdrant.

Single public function:
    retrieve(workspace_id, query, mode, top_k, document_ids, collection_name)
        -> list[RetrievalResult]

Modes:
    "dense"  — query the named dense vector only.
    "sparse" — query the named sparse vector only.
    "hybrid" — two prefetches (dense + sparse) fused with RRF via Qdrant Query API.

Always filters by workspace_id.  Optional document_ids filter narrows further.
Logs embed_ms and qdrant_ms timings.
"""

import logging
import time
import uuid
from typing import Optional

from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.schemas.search import RetrievalResult
from app.services import embedding_service, reranking_service
from app.services.vector_service import (
    DENSE_VECTOR_NAME,
    SPARSE_VECTOR_NAME,
    get_qdrant_client,
)

logger = logging.getLogger(__name__)


class RetrievalResultList(list):
    """Subclass of list that carries rerank_ms and pipeline timing metadata."""

    def __init__(
        self,
        iterable=(),
        rerank_ms: int = 0,
        embed_ms: int = 0,
        qdrant_ms: int = 0,
        candidates_count: int = 0,
    ):
        super().__init__(iterable)
        self.rerank_ms = rerank_ms
        self.embed_ms = embed_ms
        self.qdrant_ms = qdrant_ms
        self.candidates_count = candidates_count


def _build_filter(
    workspace_id: uuid.UUID,
    document_ids: Optional[list[uuid.UUID]],
) -> qmodels.Filter:
    """Build a Qdrant filter that always restricts to workspace_id."""
    must: list[qmodels.Condition] = [
        qmodels.FieldCondition(
            key="workspace_id",
            match=qmodels.MatchValue(value=str(workspace_id)),
        )
    ]
    if document_ids:
        must.append(
            qmodels.FieldCondition(
                key="document_id",
                match=qmodels.MatchAny(any=[str(d) for d in document_ids]),
            )
        )
    return qmodels.Filter(must=must)


def _point_to_result(point: qmodels.ScoredPoint, mode: str) -> RetrievalResult:
    """Map a Qdrant ScoredPoint to a RetrievalResult."""
    p = point.payload or {}
    return RetrievalResult(
        chunk_id=uuid.UUID(p["chunk_id"]),
        document_id=uuid.UUID(p["document_id"]),
        document_name=p.get("document_name", ""),
        page_number=p.get("page_number"),
        section_title=p.get("section_title"),
        text=p.get("text", ""),
        score=point.score,
        mode=mode,
    )


def retrieve(
    workspace_id: uuid.UUID,
    query: str,
    mode: str = "hybrid",
    top_k: Optional[int] = None,
    document_ids: Optional[list[uuid.UUID]] = None,
    collection_name: Optional[str] = None,
    rerank: bool = False,
) -> RetrievalResultList:
    """
    Retrieve the top-k chunks most relevant to *query* from the given workspace.

    Args:
        workspace_id:    Only return chunks belonging to this workspace.
        query:           Natural-language question or keywords.
        mode:            "dense" | "sparse" | "hybrid" (default).
        top_k:           Number of results to return when rerank=False; defaults to RETRIEVAL_TOP_K.
        document_ids:    If set, restrict to these documents only.
        collection_name: Override the Qdrant collection (used in tests).
        rerank:          If True, retrieve RETRIEVAL_TOP_K candidates then rerank to top RERANK_TOP_N.

    Returns:
        RetrievalResultList sorted by relevance (highest score first), with rerank_ms attribute.
    """
    fetch_limit = settings.RETRIEVAL_TOP_K if rerank else (top_k if top_k is not None else settings.RETRIEVAL_TOP_K)

    name = collection_name or settings.QDRANT_COLLECTION
    client = get_qdrant_client()
    ws_filter = _build_filter(workspace_id, document_ids)

    # ── 1. Embed query ─────────────────────────────────────────────────
    t0 = time.perf_counter()
    dense_vec = embedding_service.embed_query(query)
    sq = embedding_service.sparse_query(query)
    embed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info("embed_ms=%d", embed_ms)

    sparse_vec = qmodels.SparseVector(indices=sq["indices"], values=sq["values"])

    # ── 2. Query Qdrant ────────────────────────────────────────────────
    t1 = time.perf_counter()

    if mode == "dense":
        scored = client.query_points(
            collection_name=name,
            query=dense_vec,
            using=DENSE_VECTOR_NAME,
            query_filter=ws_filter,
            limit=fetch_limit,
            with_payload=True,
        ).points

    elif mode == "sparse":
        scored = client.query_points(
            collection_name=name,
            query=sparse_vec,
            using=SPARSE_VECTOR_NAME,
            query_filter=ws_filter,
            limit=fetch_limit,
            with_payload=True,
        ).points

    else:  # hybrid (default)
        prefetch_limit = settings.RETRIEVAL_TOP_K
        scored = client.query_points(
            collection_name=name,
            prefetch=[
                qmodels.Prefetch(
                    query=dense_vec,
                    using=DENSE_VECTOR_NAME,
                    filter=ws_filter,
                    limit=prefetch_limit,
                ),
                qmodels.Prefetch(
                    query=sparse_vec,
                    using=SPARSE_VECTOR_NAME,
                    filter=ws_filter,
                    limit=prefetch_limit,
                ),
            ],
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=fetch_limit,
            with_payload=True,
        ).points

    qdrant_ms = int((time.perf_counter() - t1) * 1000)
    logger.info("qdrant_ms=%d  mode=%s  results=%d", qdrant_ms, mode, len(scored))

    candidates = [_point_to_result(pt, mode) for pt in scored]
    candidates_count = len(candidates)

    # ── 3. Optional Reranking ──────────────────────────────────────────
    if rerank:
        t_rerank = time.perf_counter()
        reranked = reranking_service.rerank(
            query=query,
            results=candidates,
            top_n=settings.RERANK_TOP_N,
        )
        rerank_ms = int((time.perf_counter() - t_rerank) * 1000)
        logger.info("rerank_ms=%d  reranked_results=%d", rerank_ms, len(reranked))
        return RetrievalResultList(
            reranked,
            rerank_ms=rerank_ms,
            embed_ms=embed_ms,
            qdrant_ms=qdrant_ms,
            candidates_count=candidates_count,
        )

    return RetrievalResultList(
        candidates,
        rerank_ms=0,
        embed_ms=embed_ms,
        qdrant_ms=qdrant_ms,
        candidates_count=candidates_count,
    )
