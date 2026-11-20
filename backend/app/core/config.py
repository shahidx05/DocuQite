"""
config.py — Application settings loaded from environment / .env file.
All tuneable knobs (model names, chunk sizes, top-k) live here so there is
one place to change them, as required by RULES.md.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
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
    QDRANT_COLLECTION: str = "rag_chunks"   # override in .env; test uses rag_chunks_test

    # ------------------------------------------------------------------ #
    # LLM provider
    # ------------------------------------------------------------------ #
    LLM_PROVIDER: str = "mock"           # "gemini" | "mock" (default: "mock")
    GEMINI_API_KEY: str = ""             # set in .env when LLM_PROVIDER=gemini — never commit
    GEMINI_MODEL: str = "gemini-3.8-flash"  # current Gemini Flash model
    LLM_TIMEOUT_SECONDS: int = 30

    # LLM pricing per 1M tokens
    LLM_PRICE_INPUT_PER_1M: float = 0.0
    LLM_PRICE_OUTPUT_PER_1M: float = 0.0

    # ------------------------------------------------------------------ #
    # Embedding / reranking
    # ------------------------------------------------------------------ #
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"   # fastembed bi-encoder
    EMBEDDING_DIM: int = 384                            # output dimensions
    SPARSE_MODEL: str = "Qdrant/bm25"                  # fastembed sparse model
    EMBED_BATCH_SIZE: int = 32                          # chunks per embed call
    RERANKER_MODEL: str = "Xenova/ms-marco-MiniLM-L-6-v2"  # fastembed cross-encoder
    RERANK_ENABLED: bool = True
    MIN_RERANK_SCORE: float = 0.0                      # calibrated via score_check.py

    # ------------------------------------------------------------------ #
    # Chunking & retrieval knobs
    # ------------------------------------------------------------------ #
    CHUNKER: str = "custom"       # "custom" | "langchain" (default: "custom")
    CHUNK_SIZE: int = 1000        # characters per chunk
    CHUNK_OVERLAP: int = 150      # overlap between consecutive chunks
    RETRIEVAL_TOP_K: int = 20
    RERANK_TOP_N: int = 5
    MAX_CONTEXT_CHARS: int = 6000

    # ------------------------------------------------------------------ #
    # Upload / ingestion
    # ------------------------------------------------------------------ #
    MAX_UPLOAD_MB: int = 25
    UPLOAD_DIR: str = "data/uploads"

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
