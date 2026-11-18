"""
main.py — FastAPI application entry point.
Registers routers, configures CORS, and sets up structured logging.
Run from the backend/ directory:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging
from app.api.routes import health

configure_logging()

app = FastAPI(
    title="Enterprise RAG Platform",
    description="Non-agentic, local-first retrieval-augmented generation system.",
    version="0.1.0",
)

# Allow the Vite dev server to call our API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, prefix="/api")
