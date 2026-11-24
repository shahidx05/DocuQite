"""
schemas/document.py — Pydantic request/response models for document endpoints.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    uploaded_by: Optional[uuid.UUID]
    filename: str
    file_type: str
    file_size: int
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    status: str
    error_message: Optional[str]
    page_count: Optional[int]
    chunk_count: Optional[int]
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ChunkResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page_number: Optional[int]
    section_title: Optional[str]
    text: str
    char_count: int

    model_config = {"from_attributes": True}
