"""
config.py — Application settings loaded from environment / .env file.
All tuneable knobs (model names, chunk sizes, top-k) live here so there is
one place to change them, as required by RULES.md.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    DATABASE_URL: str = "postgresql+psycopg://rag:ragpass@localhost:5432/ragdb"

    # ------------------------------------------------------------------ #
    # Qdrant
    # ------------------------------------------------------------------ #
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "documents"  # placeholder — override in .env

    # ------------------------------------------------------------------ #
    # LLM provider
    # ------------------------------------------------------------------ #
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""             # set in .env — never commit
    GEMINI_MODEL: str = "gemini-1.5-flash"  # placeholder default

    # ------------------------------------------------------------------ #
    # Embedding / reranking
    # ------------------------------------------------------------------ #
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"  # placeholder default
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # placeholder

    # ------------------------------------------------------------------ #
    # Chunking & retrieval knobs
    # ------------------------------------------------------------------ #
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    RETRIEVAL_TOP_K: int = 20
    RERANK_TOP_N: int = 5

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    JWT_SECRET: str = "CHANGE_ME_BEFORE_PRODUCTION"
    # Token expiry in minutes (default 60 minutes = 1 hour)
    JWT_EXPIRE_MINUTES: int = 60

    # ------------------------------------------------------------------ #
    # App
    # ------------------------------------------------------------------ #
    APP_ENV: str = "development"


# Single shared instance — import this everywhere.
settings = Settings()

# Guard: refuse to start in production with the default placeholder secret.
_PLACEHOLDER = "CHANGE_ME_BEFORE_PRODUCTION"
if settings.APP_ENV == "production" and settings.JWT_SECRET == _PLACEHOLDER:
    raise RuntimeError(
        "JWT_SECRET is still the default placeholder. "
        "Set a strong secret in .env before running in production."
    )
