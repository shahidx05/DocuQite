"""
health.py — GET /api/health
Returns HTTP 200 with status "ok" or "degraded" depending on whether
Postgres and Qdrant are both reachable.  Never crashes when Docker is down.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.database import check_postgres
from app.services.vector_service import check_qdrant

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: str        # "ok" | "degraded"
    postgres: str      # "up"  | "down"
    qdrant: str        # "up"  | "down"


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """
    Probe Postgres (SELECT 1) and Qdrant (list collections).
    Always returns HTTP 200; payload indicates which services are down.
    """
    pg_up = check_postgres()
    qd_up = check_qdrant()

    pg_status = "up" if pg_up else "down"
    qd_status = "up" if qd_up else "down"
    overall = "ok" if (pg_up and qd_up) else "degraded"

    logger.info(
        "Health check — postgres=%s qdrant=%s overall=%s",
        pg_status,
        qd_status,
        overall,
    )

    return HealthResponse(status=overall, postgres=pg_status, qdrant=qd_status)
