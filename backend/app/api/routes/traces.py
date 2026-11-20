"""
api/routes/traces.py — Trace inspection and workspace metrics endpoints.

Endpoints:
    GET /api/workspaces/{workspace_id}/traces?limit=50
    GET /api/workspaces/{workspace_id}/metrics
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_workspace_member
from app.models.trace import RequestTrace
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.trace import MetricsResponse, TraceResponse
from app.services import tracing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["traces"])


@router.get(
    "/{workspace_id}/traces",
    response_model=list[TraceResponse],
)
def get_workspace_traces(
    workspace_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> list[TraceResponse]:
    """Retrieve the most recent execution traces for the specified workspace (newest first)."""
    traces = (
        db.query(RequestTrace)
        .filter(RequestTrace.workspace_id == workspace_id)
        .order_by(RequestTrace.created_at.desc())
        .limit(limit)
        .all()
    )
    return traces


@router.get(
    "/{workspace_id}/metrics",
    response_model=MetricsResponse,
)
def get_workspace_metrics(
    workspace_id: uuid.UUID,
    auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> MetricsResponse:
    """Compute aggregate execution and LLM metrics for the specified workspace."""
    traces = (
        db.query(RequestTrace)
        .filter(RequestTrace.workspace_id == workspace_id)
        .all()
    )
    return tracing_service.compute_metrics(traces)
