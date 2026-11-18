"""
test_health.py — Tests for GET /api/health (Phase 0).

Uses FastAPI's TestClient (via httpx) so no live server is required.
The test only checks the contract (HTTP 200 + expected JSON keys).
Whether Postgres/Qdrant are actually up is intentionally NOT asserted here —
that is verified by running the server manually and hitting the endpoint,
as required by RULES.md ("Never claim a feature works until a test or run proves it").
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    """Health endpoint must always return HTTP 200."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_response_has_required_keys():
    """Response body must contain status, postgres, and qdrant keys."""
    response = client.get("/api/health")
    body = response.json()
    assert "status" in body
    assert "postgres" in body
    assert "qdrant" in body


def test_health_status_is_ok_or_degraded():
    """status must be exactly 'ok' or 'degraded'."""
    response = client.get("/api/health")
    body = response.json()
    assert body["status"] in ("ok", "degraded")


def test_health_service_values_are_up_or_down():
    """postgres and qdrant values must be exactly 'up' or 'down'."""
    response = client.get("/api/health")
    body = response.json()
    assert body["postgres"] in ("up", "down")
    assert body["qdrant"] in ("up", "down")
