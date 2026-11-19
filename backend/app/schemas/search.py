"""
schemas/search.py — Request/response models for the search endpoint.
"""

import uuid
from typing import Optional

from pydantic import BaseModel


class RetrievalResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: Optional[int]
    section_title: Optional[str]
    text: str
    score: float
    mode: str  # "dense" | "sparse" | "hybrid"
    original_rank: Optional[int] = None
    rerank_score: Optional[float] = None


class SearchResponse(BaseModel):
    query: str
    mode: str
    took_ms: int
    rerank_ms: int = 0
    results: list[RetrievalResult]
