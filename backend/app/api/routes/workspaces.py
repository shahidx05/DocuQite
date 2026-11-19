"""
api/routes/workspaces.py — Workspace CRUD and member management.

POST   /api/workspaces                          — create (auth required)
GET    /api/workspaces                          — list mine
GET    /api/workspaces/{id}                     — get (member only)
DELETE /api/workspaces/{id}                     — delete (owner only)
POST   /api/workspaces/{id}/members             — add member by email (owner only)
GET    /api/workspaces/{id}/members             — list members (member only)
DELETE /api/workspaces/{id}/members/{user_id}   — remove member (owner only, not self)

Non-member requests always get 404 to avoid leaking workspace existence.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_user,
    get_db,
    require_workspace_member,
    require_workspace_owner,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.workspace import AddMemberRequest, MemberResponse, WorkspaceCreate, WorkspaceResponse
from app.services.vector_service import delete_by_workspace

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    body: WorkspaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    """Create a workspace and make the creator the owner member."""
    ws = Workspace(name=body.name, owner_id=current_user.id)
    db.add(ws)
    db.flush()  # get ws.id before creating the member row

    member = WorkspaceMember(workspace_id=ws.id, user_id=current_user.id, role="owner")
    db.add(member)
    db.commit()
    db.refresh(ws)
    logger.info("Workspace created: id=%s owner=%s", ws.id, current_user.id)
    return WorkspaceResponse.model_validate(ws)


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceResponse]:
    """Return only workspaces where the current user is a member."""
    rows = (
        db.query(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .filter(WorkspaceMember.user_id == current_user.id)
        .all()
    )
    return [WorkspaceResponse.model_validate(ws) for ws in rows]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_and_member: tuple = Depends(require_workspace_member),
) -> WorkspaceResponse:
    workspace, _ = workspace_and_member
    return WorkspaceResponse.model_validate(workspace)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    db: Session = Depends(get_db),
    workspace_and_member: tuple = Depends(require_workspace_owner),
) -> None:
    workspace, _ = workspace_and_member
    # Remove all vectors for this workspace (best-effort).
    try:
        delete_by_workspace(workspace.id)
    except Exception as e:
        logger.warning("Could not delete vectors for workspace=%s: %s", workspace.id, e)
    db.delete(workspace)
    db.commit()
    logger.info("Workspace deleted: id=%s", workspace.id)


@router.post("/{workspace_id}/members", response_model=MemberResponse, status_code=201)
def add_member(
    body: AddMemberRequest,
    db: Session = Depends(get_db),
    workspace_and_member: tuple = Depends(require_workspace_owner),
) -> MemberResponse:
    """Add an existing user to the workspace by email (owner only)."""
    workspace, _ = workspace_and_member

    target = db.query(User).filter(User.email == body.email.lower()).first()
    if target is None:
        raise HTTPException(status_code=404, detail="User not found.")

    existing = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == target.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member.")

    new_member = WorkspaceMember(workspace_id=workspace.id, user_id=target.id, role="member")
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return MemberResponse.model_validate(new_member)


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
def list_members(
    db: Session = Depends(get_db),
    workspace_and_member: tuple = Depends(require_workspace_member),
) -> list[MemberResponse]:
    workspace, _ = workspace_and_member
    rows = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace.id)
        .all()
    )
    return [MemberResponse.model_validate(m) for m in rows]


@router.delete("/{workspace_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    workspace_and_member: tuple = Depends(require_workspace_owner),
) -> None:
    """Remove a member (owner only). The owner cannot remove themselves."""
    workspace, owner_member = workspace_and_member

    if user_id == owner_member.user_id:
        raise HTTPException(status_code=400, detail="The workspace owner cannot be removed.")

    target_member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user_id,
        )
        .first()
    )
    if target_member is None:
        raise HTTPException(status_code=404, detail="Member not found.")

    db.delete(target_member)
    db.commit()
