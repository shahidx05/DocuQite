"""
conftest.py — pytest fixtures shared across all Phase 1 tests.

IMPORTANT: uses ragdb_test, never touches ragdb (the dev database).
The test DB is created if it doesn't exist, tables are created fresh for
each test session, and all tests run inside a rolled-back transaction so
rows are never committed permanently.
"""

import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import Base
from app.api.deps import get_db
from app.main import app

# ── Test database URL ──────────────────────────────────────────────────
# Replace the DB name with ragdb_test; keep everything else identical.
TEST_DB_URL = settings.DATABASE_URL.replace("/ragdb", "/ragdb_test")

# Engine that connects to the postgres maintenance DB to run CREATE DATABASE
_ADMIN_URL = settings.DATABASE_URL.replace("/ragdb", "/postgres")


def _ensure_test_db() -> None:
    """Create ragdb_test if it doesn't exist. Never touches ragdb."""
    admin_engine = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'ragdb_test'")
        ).fetchone()
        if not exists:
            conn.execute(text("CREATE DATABASE ragdb_test"))
    admin_engine.dispose()


# Run once at session start
_ensure_test_db()

# Engine for the test DB — tables recreated per session
_test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
Base.metadata.create_all(_test_engine)

_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture()
def db():
    """
    Each test gets a fresh transaction that is always rolled back.
    This means no row ever persists between tests and ragdb is never touched.
    """
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """TestClient with the DB dependency overridden to use the test session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass  # rollback handled by the db fixture

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
