"""
tests/conftest.py — pytest fixtures shared across all phases.

IMPORTANT: uses ragdb_test, never touches ragdb (the dev database).
Tests run inside rolled-back transactions so rows never persist between tests.
Phase 2 adds a tmp_upload_dir fixture so upload tests never write to data/uploads.
"""

import uuid
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import Base
from app.api.deps import get_db
from app.main import app

# ── Test database URL ──────────────────────────────────────────────────
TEST_DB_URL = settings.DATABASE_URL.replace("/ragdb", "/ragdb_test")
_ADMIN_URL  = settings.DATABASE_URL.replace("/ragdb", "/postgres")


def _ensure_test_db() -> None:
    admin_engine = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'ragdb_test'")
        ).fetchone()
        if not exists:
            conn.execute(text("CREATE DATABASE ragdb_test"))
    admin_engine.dispose()


_ensure_test_db()

_test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
Base.metadata.create_all(_test_engine)

_TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_test_engine)


@pytest.fixture()
def db():
    connection = _test_engine.connect()
    transaction = connection.begin()
    session = _TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def tmp_upload_dir(tmp_path, monkeypatch):
    """
    Override the storage singleton to write into pytest's tmp_path.
    This prevents any test file from landing in data/uploads.
    """
    from app.services import storage_service
    from app.api.routes import documents as doc_routes

    local = storage_service.LocalStorage(str(tmp_path))
    monkeypatch.setattr(storage_service, "storage", local)
    monkeypatch.setattr(doc_routes, "storage", local)
    return tmp_path
