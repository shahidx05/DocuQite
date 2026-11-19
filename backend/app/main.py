"""
main.py — FastAPI application entry point.
Registers routers, configures CORS, and sets up structured logging.
Run from the backend/ directory:
    uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.logging import configure_logging
from app.api.routes import health, auth, workspaces, documents, search

configure_logging()
logger = logging.getLogger(__name__)

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


# ── Centralised error handler ──────────────────────────────────────────
# FastAPI already returns {"detail": ...} for HTTPException by default.
# This handler catches unexpected server errors and logs them without
# leaking stack traces to the client.
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ── Routers ────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(workspaces.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(search.router, prefix="/api")

