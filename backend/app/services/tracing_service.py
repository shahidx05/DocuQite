"""
services/tracing_service.py — Request tracing and LLM metrics recording.

Captures per-request stage timings, tokens, estimated costs, and metadata.
Guarantees:
- A tracing failure NEVER fails the user request.
- Failed requests are recorded with a short error message.
- Question text and document chunks are NEVER stored (only question_length).
- Metrics handle zero traces without crashing.
"""

import logging
import math
import uuid
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.trace import RequestTrace
from app.schemas.trace import MetricsResponse, PercentileMetric

logger = logging.getLogger(__name__)


def calculate_cost(input_tokens: int, output_tokens: int, provider: str) -> float:
    """Compute estimated cost in USD based on configured token pricing."""
    if provider == "mock":
        return 0.0
    cost = (
        (input_tokens * settings.LLM_PRICE_INPUT_PER_1M)
        + (output_tokens * settings.LLM_PRICE_OUTPUT_PER_1M)
    ) / 1_000_000.0
    return float(cost)


def record_trace(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    source: str,
    question_length: int,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    rewrite_ms: int = 0,
    embed_ms: int = 0,
    qdrant_ms: int = 0,
    rerank_ms: int = 0,
    llm_ms: int = 0,
    total_ms: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: Optional[float] = None,
    candidates_count: int = 0,
    abstained: bool = False,
    top_rerank_score: Optional[float] = None,
    error: Optional[str] = None,
    db: Optional[Session] = None,
) -> Optional[RequestTrace]:
    """
    Persist a trace for a completed or failed request.
    Catches all exceptions so tracing errors never fail the main request.
    """
    effective_provider = provider or settings.LLM_PROVIDER
    effective_model = model or settings.GEMINI_MODEL

    if estimated_cost_usd is None:
        estimated_cost_usd = calculate_cost(input_tokens, output_tokens, effective_provider)

    # Truncate error if present to ensure it's a short error message
    short_error = error[:255] if error else None

    trace = RequestTrace(
        workspace_id=workspace_id,
        user_id=user_id,
        source=source,
        provider=effective_provider,
        model=effective_model,
        question_length=question_length,
        rewrite_ms=rewrite_ms,
        embed_ms=embed_ms,
        qdrant_ms=qdrant_ms,
        rerank_ms=rerank_ms,
        llm_ms=llm_ms,
        total_ms=total_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        candidates_count=candidates_count,
        abstained=abstained,
        top_rerank_score=top_rerank_score,
        error=short_error,
    )

    try:
        if db is not None:
            with db.begin_nested():
                db.add(trace)
            db.commit()
            db.refresh(trace)
        else:
            with SessionLocal() as session:
                session.add(trace)
                session.commit()
                session.refresh(trace)
        return trace
    except Exception as exc:
        logger.error("Failed to record request trace: %s", exc)
        return None


def calculate_percentile(values: Sequence[float | int], p: float) -> float:
    """
    Compute percentile using linear interpolation (similar to numpy/Postgres percentile_cont).
    p is between 0.0 and 1.0 (e.g., 0.50 for p50, 0.95 for p95).
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])

    idx = (n - 1) * p
    low = int(math.floor(idx))
    high = int(math.ceil(idx))
    weight = idx - low
    result = float(sorted_vals[low] * (1.0 - weight) + sorted_vals[high] * weight)
    return round(result, 2)


def compute_metrics(traces: Sequence[RequestTrace]) -> MetricsResponse:
    """
    Compute aggregate metrics and percentiles over a collection of traces.
    Handles empty trace lists safely without division by zero.
    """
    request_count = len(traces)
    if request_count == 0:
        zero_metric = PercentileMetric(p50=0.0, p95=0.0)
        return MetricsResponse(
            request_count=0,
            abstain_rate=0.0,
            error_rate=0.0,
            total_estimated_cost_usd=0.0,
            avg_input_tokens=0.0,
            avg_output_tokens=0.0,
            tokens_per_second=0.0,
            total_ms=zero_metric,
            rewrite_ms=zero_metric,
            embed_ms=zero_metric,
            qdrant_ms=zero_metric,
            rerank_ms=zero_metric,
            llm_ms=zero_metric,
        )

    abstain_count = sum(1 for t in traces if t.abstained)
    error_count = sum(1 for t in traces if t.error is not None)
    total_cost = sum(t.estimated_cost_usd for t in traces)
    total_in_tokens = sum(t.input_tokens for t in traces)
    total_out_tokens = sum(t.output_tokens for t in traces)
    total_llm_ms = sum(t.llm_ms for t in traces)

    tokens_per_second = (
        round(total_out_tokens / (total_llm_ms / 1000.0), 2)
        if total_llm_ms > 0
        else 0.0
    )

    def _stage_percentile(getter) -> PercentileMetric:
        vals = [getter(t) for t in traces]
        return PercentileMetric(
            p50=calculate_percentile(vals, 0.50),
            p95=calculate_percentile(vals, 0.95),
        )

    return MetricsResponse(
        request_count=request_count,
        abstain_rate=round(abstain_count / request_count, 4),
        error_rate=round(error_count / request_count, 4),
        total_estimated_cost_usd=round(total_cost, 6),
        avg_input_tokens=round(total_in_tokens / request_count, 2),
        avg_output_tokens=round(total_out_tokens / request_count, 2),
        tokens_per_second=tokens_per_second,
        total_ms=_stage_percentile(lambda t: t.total_ms),
        rewrite_ms=_stage_percentile(lambda t: t.rewrite_ms),
        embed_ms=_stage_percentile(lambda t: t.embed_ms),
        qdrant_ms=_stage_percentile(lambda t: t.qdrant_ms),
        rerank_ms=_stage_percentile(lambda t: t.rerank_ms),
        llm_ms=_stage_percentile(lambda t: t.llm_ms),
    )
