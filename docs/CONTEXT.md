# Project context (read before doing anything)

Enterprise RAG platform, non-agentic, local-first. Stack: FastAPI, SQLAlchemy,
Alembic, Postgres, Qdrant, fastembed (local), React+Vite+JavaScript later.
Gemini API is used only for answer generation (Phase 5).

DONE AND COMMITTED:
- Phase 0: skeleton, config, /api/health
- Phase 1: auth (JWT, argon2), workspaces, members, 404 for non-members
- Phase 2: upload, storage, parsing (PDF/DOCX/PPTX), cleaning, chunking
- Phase 3: embeddings (BAAI/bge-small-en-v1.5, 384-dim), sparse (Qdrant/bm25),
  one shared Qdrant collection with named dense+sparse vectors, workspace_id filter
- Phase 4A: hybrid retrieval (dense + sparse, RRF) via retrieve() and
  GET /api/workspaces/{id}/search
- Phase 4B: reranking with fastembed 0.5.1 TextCrossEncoder
  (Xenova/ms-marco-MiniLM-L-6-v2)
Tests: 115 passing. Test DB: ragdb_test. Test Qdrant collection: rag_chunks_test.

NEXT: Phase 5 = Gemini answers, citations, abstention. Not started.

WORKING STYLE:
- One phase at a time; stop and wait for my test after each.
- Never write "continue" behaviour: do not start the next phase on your own.
- No new packages without asking. Never read or print .env. Never commit.
- Never run destructive commands without asking.
- Report only real test output.