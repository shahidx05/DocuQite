"""
api/routes/search.py — Hybrid search endpoint for a workspace.

GET /api/workspaces/{workspace_id}/search
    ?q=<query>          non-empty, max 500 chars
    &mode=hybrid        dense | sparse | hybrid
    &top_k=10           1–30 (default 10)

Access control: member-only via require_workspace_member (non-members get 404).
Response: SearchResponse — query, mode, took_ms, results[].
"""

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import require_workspace_member
from app.core.config import settings
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.search import SearchResponse
from app.services import retrieval_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["search"])


@router.get("/{workspace_id}/search", response_model=SearchResponse)
def search_workspace(
    workspace_id: uuid.UUID,
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    mode: str = Query("hybrid", pattern="^(dense|sparse|hybrid)$", description="Retrieval mode"),
    top_k: int = Query(10, ge=1, le=30, description="Number of results to return"),
    rerank: Optional[bool] = Query(default=None, description="Apply cross-encoder reranking"),
    _auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
) -> SearchResponse:
    """
    Search the workspace using the specified retrieval mode.

    Returns the top-k most relevant chunks with scores, page numbers,
    and section titles.  This is a debug/evaluation endpoint; the chat
    API (Phase 5) will call retrieve() directly.
    """
    if rerank is None:
        rerank = settings.RERANK_ENABLED

    t_start = time.perf_counter()

    results = retrieval_service.retrieve(
        workspace_id=workspace_id,
        query=q,
        mode=mode,
        top_k=top_k,
        rerank=rerank,
    )

    took_ms = int((time.perf_counter() - t_start) * 1000)
    rerank_ms = getattr(results, "rerank_ms", 0)
    logger.info(
        "search workspace_id=%s mode=%s top_k=%d rerank=%s took_ms=%d rerank_ms=%d results=%d",
        workspace_id,
        mode,
        top_k,
        rerank,
        took_ms,
        rerank_ms,
        len(results),
    )

    return SearchResponse(
        query=q,
        mode=mode,
        took_ms=took_ms,
        rerank_ms=rerank_ms,
        results=results,
    )
