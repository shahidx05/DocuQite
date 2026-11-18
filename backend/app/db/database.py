"""
database.py — SQLAlchemy engine and session factory.
Only the engine is needed in Phase 0 (for the health-check SELECT 1).
Full ORM models and migrations come in later phases.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # automatically reconnects dropped connections
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class for all ORM models (used in later phases)."""
    pass


def check_postgres() -> bool:
    """Return True if Postgres is reachable, False otherwise."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
