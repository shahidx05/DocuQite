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
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_workspace_member
from app.models.workspace import Workspace, WorkspaceMember
from app.rag.generation import answer
from app.schemas.ask import AskRequest, AskResponse
from app.services.llm_service import LLMError, LLMKeyMissingError, LLMRateLimitError, LLMTimeoutError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["qa"])


@router.post("/{workspace_id}/ask", response_model=AskResponse)
def ask_workspace(
    workspace_id: uuid.UUID,
    body: AskRequest,
    _auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
) -> AskResponse:
    """
    Generate a grounded answer with citations from the workspace's documents.
    """
    try:
        return answer(workspace_id=workspace_id, question=body.question)
    except LLMKeyMissingError as exc:
        logger.error("LLM key missing: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GEMINI_API_KEY is not configured on the server.",
        ) from exc
    except LLMRateLimitError as exc:
        logger.warning("LLM rate limit: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM service rate limit exceeded. Please try again later.",
        ) from exc
    except LLMTimeoutError as exc:
        logger.warning("LLM timeout: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM generation timed out. Please try again.",
        ) from exc
    except LLMError as exc:
        logger.error("LLM failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM generation failed: {exc}",
        ) from exc
