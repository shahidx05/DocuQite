# Project Rules

- Non-agentic RAG. No agents, no multi-agent, no autonomous tool use.
- Python 3.12, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Qdrant, fastembed.
- Frontend: React + Vite + JavaScript (no TypeScript) + Tailwind.
- Build ONE phase at a time. After finishing, stop and wait for my test.
- Do not add new packages without asking me and explaining why.
- Write tests for each phase. Never claim a feature works until a test or run proves it.
- Never invent metrics. Report only real measurements.
- Secrets only in .env. Never commit them. Never read or print .env.
- Keep model names, chunk sizes and top-k values in config.
- Never run destructive commands (rm -rf, docker compose down -v, docker volume rm)
  without asking me first.
- Keep code simple enough for me to explain in an interview.
- Work ONLY inside this project folder. Never read, search, copy from, or - write to any other folder on disk. If a required file is missing, STOP and tell me; do not look for it elsewhere.