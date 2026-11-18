"""
schemas/workspace.py — Pydantic request/response models for workspace endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Request bodies ─────────────────────────────────────────────────────

class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class AddMemberRequest(BaseModel):
    email: str  # looked up by email server-side


# ── Response bodies ────────────────────────────────────────────────────

class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    role: str

    model_config = {"from_attributes": True}
