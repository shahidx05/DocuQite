# DocuMind Knowledge Studio (Frontend)

A modern, responsive React interface for the document knowledge workspace and grounded conversational intelligence engine.

---

## Features

- **Authentication & Security**:
  - Email/password user registration and login.
  - JWT token storage with auto-header injection and 401 handling.
  - Quick-fill demo credentials.

- **Workspace Management**:
  - Workspace selector with quick switching.
  - Create new isolated workspaces.
  - Team member management: invite by email, view roles, remove members.
  - Workspace deletion for workspace owners.

- **Document Ingestion & Management**:
  - Drag-and-drop upload supporting `.pdf`, `.docx`, and `.pptx` up to 25MB.
  - Real-time ingestion status tracking (`PENDING`, `PROCESSING`, `READY`, `FAILED`).
  - Document metadata: file size, page count, chunk count, timestamp, and error details.
  - **Chunk Inspector**: Paginated text chunk viewer displaying chunk index, page number, section title, and char count.
  - Retry ingestion trigger for failed uploads.
  - Document deletion with vector cascade.

- **Grounded Conversational Assistant**:
  - Multi-session chat history per workspace.
  - Dynamic follow-up question resolution and conversation persistence.
  - Grounded answer generation with abstention detection.
  - **Interactive Citations**: Clickable source badges displaying source document, page number, section title, and highlighted passage snippet.
  - Generation metrics: Retrieval latency, LLM latency, total latency, and input/output token counts.

- **Search & Retrieval Explorer**:
  - Interactive evaluation tool for dense, sparse, and hybrid search.
  - Adjustable Top-K candidates slider (1–30).
  - Cross-Encoder reranker toggle (`rerank=true/false`).
  - Score transparency: compare initial retrieval scores vs. cross-encoder rerank scores.

- **Direct Grounded Q&A**:
  - One-shot question answering evaluation pipeline.

---

## Getting Started

### 1. Install Dependencies
```bash
npm install
```

### 2. Start Development Server
```bash
npm run dev
```
The app runs at `http://localhost:5173`. API requests to `/api` are automatically proxied to the backend at `http://localhost:8000`.

### 3. Production Build
```bash
npm run build
```
Build output is generated in `dist/`.
