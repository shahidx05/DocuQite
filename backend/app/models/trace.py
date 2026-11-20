"""
models/trace.py — RequestTrace ORM model for Phase 6 metrics and tracing.
Stores per-request execution timings, token metrics, cost, and stage stats.
Never stores document text, answers, or raw query text (only question_length).
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class RequestTrace(Base):
    __tablename__ = "request_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # "ask" | "chat"
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # "mock" | "gemini"
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    question_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rewrite_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embed_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qdrant_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rerank_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    candidates_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abstained: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    top_rerank_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        index=True,
    )
