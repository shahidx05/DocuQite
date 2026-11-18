"""
api/deps.py — Reusable FastAPI dependencies.

get_db          — yields a SQLAlchemy session
get_current_user — parses Bearer token, returns the User row
require_workspace_member — returns (workspace, member_row); 404 if not a member
require_workspace_owner  — same but 403 if not owner role

Access-control design note (from RULES.md / spec):
  If a user is not a member of a workspace, return 404 (not 403) so workspace
  existence is not leaked.
"""

import logging
import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

logger = logging.getLogger(__name__)

_bearer = HTTPBearer()


# ── Database session ───────────────────────────────────────────────────

def get_db():
    """Yield a DB session and close it when the request is done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Current-user dependency ────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Extract and validate the Bearer JWT. Returns the User row.
    Raises 401 on any token problem (expired, tampered, missing).
    Never logs the token itself.
    """
    _401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id: str = payload.get("sub")
        if not user_id:
            raise _401
    except jwt.PyJWTError:
        raise _401

    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise _401
    return user


# ── Workspace access dependencies ──────────────────────────────────────

def require_workspace_member(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[Workspace, WorkspaceMember]:
    """
    Return (workspace, member_row) if current_user is a member.
    Returns 404 either way so workspace existence is not leaked to non-members.
    """
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
        .first()
    )
    if member is None:
        # 404 — do not reveal that the workspace exists
        raise HTTPException(status_code=404, detail="Workspace not found.")

    return workspace, member


def require_workspace_owner(
    workspace_and_member: tuple[Workspace, WorkspaceMember] = Depends(require_workspace_member),
) -> tuple[Workspace, WorkspaceMember]:
    """Gate on owner role; 403 since the user already knows they're a member."""
    workspace, member = workspace_and_member
    if member.role != "owner":
        raise HTTPException(status_code=403, detail="Owner permission required.")
    return workspace, member
