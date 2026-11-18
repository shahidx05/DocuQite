# Enterprise RAG Platform

A **non-agentic, local-first** retrieval-augmented generation system built with
FastAPI, PostgreSQL, Qdrant, and React + Vite.  The goal is to let you upload
documents, embed them locally (no cloud embeddings required), and query them with
a large language model — all running on your own machine, for free.

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.12 |
| Docker Desktop | Running |
| Node.js | 18+ (Phase 2+) |
| Git | Any |

---

## Quick Start

### 1. Start Docker services (Postgres + Qdrant)

```bash
docker compose up -d
docker compose ps
```

### 2. Create and activate the Python virtual environment

```bash
# From the project root
py -3.12 -m venv backend/.venv

# Windows (PowerShell)
backend\.venv\Scripts\Activate.ps1

# macOS / Linux
source backend/.venv/bin/activate
```

### 3. Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure environment

```bash
# Copy the example and fill in your values
copy .env.example .env     # Windows
cp  .env.example .env      # macOS/Linux
```

Edit `.env` and set at minimum `GEMINI_API_KEY` (or leave empty for Phase 0).

### 5. Start the API server

```bash
# Run from the backend/ directory
uvicorn app.main:app --reload
```

The API is now available at **http://localhost:8000**.

### 6. Run the test suite

```bash
# From the backend/ directory, with the venv active
pytest tests/ -v
```

---

## Endpoints (Phase 0)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness + dependency check |

---

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── api/routes/   # FastAPI routers
│   │   ├── core/         # Config & logging
│   │   ├── db/           # SQLAlchemy engine
│   │   └── services/     # Qdrant client
│   ├── tests/
│   └── requirements.txt
├── docs/
│   └── RULES.md          # Development rules — read before changing anything
├── docker-compose.yml
└── .env.example
```
