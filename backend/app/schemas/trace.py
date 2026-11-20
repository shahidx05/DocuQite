"""
schemas/trace.py — Request & response schemas for traces and aggregated metrics.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TraceResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    source: str
    provider: str
    model: str
    question_length: int
    rewrite_ms: int
    embed_ms: int
    qdrant_ms: int
    rerank_ms: int
    llm_ms: int
    total_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    candidates_count: int
    abstained: bool
    top_rerank_score: Optional[float] = None
    error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PercentileMetric(BaseModel):
    p50: float
    p95: float


class MetricsResponse(BaseModel):
    request_count: int
    abstain_rate: float
    error_rate: float
    total_estimated_cost_usd: float
    avg_input_tokens: float
    avg_output_tokens: float
    tokens_per_second: float

    # Percentiles for total and per-stage latencies
    total_ms: PercentileMetric
    rewrite_ms: PercentileMetric
    embed_ms: PercentileMetric
    qdrant_ms: PercentileMetric
    rerank_ms: PercentileMetric
    llm_ms: PercentileMetric
