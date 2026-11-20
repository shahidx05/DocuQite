"""
api/routes/ask.py — Grounded Q&A endpoint.

POST /api/workspaces/{workspace_id}/ask
    body: { "question": str } (1–500 chars)

Access control:
    require_workspace_member (non-members get 404).
Response:
    AskResponse — answer, abstained, citations, timings, tokens.
"""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_workspace_member
from app.models.workspace import Workspace, WorkspaceMember
from app.rag.generation import answer
from app.schemas.ask import AskRequest, AskResponse
from app.services import tracing_service
from app.services.llm_service import LLMError, LLMKeyMissingError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["qa"])


@router.post("/{workspace_id}/ask", response_model=AskResponse)
def ask_workspace(
    workspace_id: uuid.UUID,
    body: AskRequest,
    _auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> AskResponse:
    """
    Generate a grounded answer with citations from the workspace's documents.
    """
    _, member = _auth
    user_id = member.user_id
    q_len = len(body.question)
    t_start = time.perf_counter()

    try:
        res = answer(workspace_id=workspace_id, question=body.question)
        total_ms = int((time.perf_counter() - t_start) * 1000)

        try:
            tracing_service.record_trace(
                workspace_id=workspace_id,
                user_id=user_id,
                source="ask",
                question_length=q_len,
                embed_ms=res.timings.embed_ms,
                qdrant_ms=res.timings.qdrant_ms,
                rerank_ms=res.timings.rerank_ms,
                llm_ms=res.timings.llm_ms,
                total_ms=total_ms,
                input_tokens=res.tokens.input_tokens,
                output_tokens=res.tokens.output_tokens,
                candidates_count=res.candidates_count,
                abstained=res.abstained,
                top_rerank_score=res.top_rerank_score,
                error=None,
                db=db,
            )
        except Exception as t_err:
            logger.error("Failed to record trace for /ask: %s", t_err)

        return res
    except LLMKeyMissingError as exc:
        total_ms = int((time.perf_counter() - t_start) * 1000)
        try:
            tracing_service.record_trace(
                workspace_id=workspace_id,
                user_id=user_id,
                source="ask",
                question_length=q_len,
                total_ms=total_ms,
                error=str(exc),
                db=db,
            )
        except Exception as t_err:
            logger.error("Failed to record trace for /ask error: %s", t_err)
        logger.error("LLM key missing: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GEMINI_API_KEY is not configured on the server.",
        ) from exc
    except LLMRateLimitError as exc:
        total_ms = int((time.perf_counter() - t_start) * 1000)
        try:
            tracing_service.record_trace(
                workspace_id=workspace_id,
                user_id=user_id,
                source="ask",
                question_length=q_len,
                total_ms=total_ms,
                error=str(exc),
                db=db,
            )
        except Exception as t_err:
            logger.error("Failed to record trace for /ask error: %s", t_err)
        logger.warning("LLM rate limit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM service rate limit exceeded. Please try again later.",
        ) from exc
    except LLMTimeoutError as exc:
        total_ms = int((time.perf_counter() - t_start) * 1000)
        try:
            tracing_service.record_trace(
                workspace_id=workspace_id,
                user_id=user_id,
                source="ask",
                question_length=q_len,
                total_ms=total_ms,
                error=str(exc),
                db=db,
            )
        except Exception as t_err:
            logger.error("Failed to record trace for /ask error: %s", t_err)
        logger.warning("LLM timeout: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM generation timed out. Please try again.",
        ) from exc
    except LLMError as exc:
        total_ms = int((time.perf_counter() - t_start) * 1000)
        try:
            tracing_service.record_trace(
                workspace_id=workspace_id,
                user_id=user_id,
                source="ask",
                question_length=q_len,
                total_ms=total_ms,
                error=str(exc),
                db=db,
            )
        except Exception as t_err:
            logger.error("Failed to record trace for /ask error: %s", t_err)
        logger.error("LLM failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM generation failed: {exc}",
        ) from exc
    except Exception as exc:
        total_ms = int((time.perf_counter() - t_start) * 1000)
        try:
            tracing_service.record_trace(
                workspace_id=workspace_id,
                user_id=user_id,
                source="ask",
                question_length=q_len,
                total_ms=total_ms,
                error=str(exc),
                db=db,
            )
        except Exception as t_err:
            logger.error("Failed to record trace for /ask error: %s", t_err)
        raise
