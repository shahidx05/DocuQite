"""
api/routes/chats.py — Chat sessions and conversational messaging routes.

Endpoints:
    POST   /api/workspaces/{workspace_id}/chats  -> create session
    GET    /api/workspaces/{workspace_id}/chats   -> list user's sessions in workspace
    GET    /api/chats/{chat_id}                  -> get session + messages
    DELETE /api/chats/{chat_id}                  -> delete session + cascade messages
    POST   /api/chats/{chat_id}/messages         -> post message, rewrite if follow-up, answer, persist
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_workspace_member
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.rag.generation import answer
from app.rag.rewrite import rewrite_question
from app.schemas.chat import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionDetailResponse,
    ChatSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chats"])


def _get_user_chat_session(
    chat_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> ChatSession:
    """
    Fetch a chat session ensuring:
      1. Session exists (404 otherwise)
      2. Session belongs to the requesting user (404 otherwise — prevents leaking existence)
      3. User is an active member of the workspace (404 otherwise)
    """
    chat = db.get(ChatSession, chat_id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    if chat.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    is_member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == chat.workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found.",
        )

    return chat


# ── Workspace Chat Sessions ─────────────────────────────────────────────

@router.post(
    "/workspaces/{workspace_id}/chats",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(
    workspace_id: uuid.UUID,
    body: Optional[ChatSessionCreate] = None,
    auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> ChatSessionResponse:
    """Create a new chat session in the specified workspace for the current user."""
    _, member = auth
    title = (body.title.strip() if body and body.title and body.title.strip() else "New Chat")

    session = ChatSession(
        workspace_id=workspace_id,
        user_id=member.user_id,
        title=title,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.get(
    "/workspaces/{workspace_id}/chats",
    response_model=list[ChatSessionResponse],
)
def list_chat_sessions(
    workspace_id: uuid.UUID,
    auth: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
    db: Session = Depends(get_db),
) -> list[ChatSessionResponse]:
    """List all chat sessions belonging to the current user in this workspace."""
    _, member = auth
    sessions = (
        db.query(ChatSession)
        .filter(
            ChatSession.workspace_id == workspace_id,
            ChatSession.user_id == member.user_id,
        )
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return sessions


# ── Individual Chat Session & Messaging ─────────────────────────────────

@router.get(
    "/chats/{chat_id}",
    response_model=ChatSessionDetailResponse,
)
def get_chat_session(
    chat_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatSessionDetailResponse:
    """Get chat session details along with all messages in chronological order."""
    chat = _get_user_chat_session(chat_id, current_user.id, db)
    return chat


@router.delete(
    "/chats/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_chat_session(
    chat_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Delete a chat session and all its associated messages."""
    chat = _get_user_chat_session(chat_id, current_user.id, db)
    db.delete(chat)
    db.commit()


@router.post(
    "/chats/{chat_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_200_OK,
)
def post_chat_message(
    chat_id: uuid.UUID,
    body: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """
    Add a user message, run follow-up question rewriting (if history exists),
    retrieve candidates, generate a grounded answer, persist both messages,
    and return the assistant message.
    """
    chat = _get_user_chat_session(chat_id, current_user.id, db)

    # 1. Fetch prior messages for this session
    prior_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == chat.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    # 2. Update title if this is the first message or still default
    if not prior_messages or chat.title == "New Chat":
        chat.title = body.question[:60].strip()

    # 3. Follow-up rewriting: rewrite if history exists, skip if first message
    if prior_messages:
        rewritten_question = rewrite_question(question=body.question, history=prior_messages)
    else:
        rewritten_question = body.question

    # 4. Run RAG retrieval + generation using the rewritten question
    rag_result = answer(workspace_id=chat.workspace_id, question=rewritten_question)

    # 5. Persist user message
    user_msg = ChatMessage(
        session_id=chat.id,
        role="user",
        content=body.question,
    )
    db.add(user_msg)

    # 6. Persist assistant message
    citations_data = (
        [c.model_dump(mode="json") for c in rag_result.citations] if rag_result.citations else None
    )
    metadata_dict = {
        "rewritten_question": rewritten_question,
        "timings": rag_result.timings.model_dump() if rag_result.timings else None,
        "tokens": rag_result.tokens.model_dump() if rag_result.tokens else None,
    }

    assistant_msg = ChatMessage(
        session_id=chat.id,
        role="assistant",
        content=rag_result.answer,
        citations=citations_data,
        abstained=rag_result.abstained,
        meta=metadata_dict,
    )
    db.add(assistant_msg)

    # 7. Update chat session timestamp
    chat.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant_msg)

    return assistant_msg
