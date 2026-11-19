"""
schemas/ask.py — Request/response schemas for grounded Q&A.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Question to answer from documents")


class Citation(BaseModel):
    n: int
    document_id: uuid.UUID
    document_name: str
    page_number: Optional[int]
    section_title: Optional[str]
    snippet: str


class AskTimings(BaseModel):
    retrieval_ms: int
    llm_ms: int
    total_ms: int


class AskTokens(BaseModel):
    input_tokens: int
    output_tokens: int


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    citations: list[Citation]
    timings: AskTimings
    tokens: AskTokens
