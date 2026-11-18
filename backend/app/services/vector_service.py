"""
vector_service.py — Qdrant client factory and connectivity check.
Phase 0: only a ping.  Collection creation / upsert come in later phases.
"""

import logging

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_qdrant_client() -> QdrantClient:
    """Return a configured Qdrant client (no network call yet)."""
    return QdrantClient(url=settings.QDRANT_URL)


def check_qdrant() -> bool:
    """Return True if Qdrant is reachable, False otherwise."""
    try:
        client = get_qdrant_client()
        # get_collections() is a lightweight call that hits the REST API
        client.get_collections()
        return True
    except Exception as exc:
        logger.warning("Qdrant ping failed: %s", exc)
        return False
