"""
rag/ingestion.py — Full ingestion pipeline: parse → clean → chunk → embed → index.

State machine:
  PENDING → PROCESSING → (parse → clean → chunk → DB write) → CHUNKED
           → INDEXING  → (embed → upsert Qdrant)            → COMPLETED
           → FAILED    (on any error in either stage)

Retry: deletes old DB chunks AND old Qdrant vectors first, then reruns from PENDING.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Chunk, Document, DocumentStatus
from app.rag.chunking import chunk_document
from app.rag.cleaning import clean_document
from app.rag.parsing import parse_document
from app.services import embedding_service
from app.services.vector_service import (
    delete_by_document,
    ensure_collection,
    upsert_chunks,
)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _build_embed_text(document_name: str, section_title: str | None, chunk_text: str) -> str:
    """
    Build the text that will be fed to the embedding model.
    Format: "{document_name} | {section_title}\\n{chunk_text}"
    If section_title is None, the prefix is just "{document_name}\\n{chunk_text}".
    The stored chunk.text is NEVER changed.
    """
    if section_title:
        prefix = f"{document_name} | {section_title}"
    else:
        prefix = document_name
    return f"{prefix}\n{chunk_text}"


def run_ingestion(document_id: uuid.UUID, db: Session, storage_path: str) -> None:
    """
    Entry point called by the BackgroundTask.
    Fetches the Document row, runs the full pipeline, and writes the result back.
    db is a NEW session created inside the background task (not the request session).
    """
    doc = db.get(Document, document_id)
    if doc is None:
        logger.error("Ingestion: document %s not found.", document_id)
        return

    # Mark as PROCESSING
    doc.status = DocumentStatus.PROCESSING
    doc.updated_at = _now()
    db.commit()

    file_path = Path(storage_path)

    try:
        # ── Parse ──────────────────────────────────────────────────────
        t0 = time.monotonic()
        parsed = parse_document(file_path, doc.file_type)
        parse_ms = int((time.monotonic() - t0) * 1000)
        logger.info("doc=%s parse=%dms pages=%d", document_id, parse_ms, parsed.page_count)

        # ── Clean ──────────────────────────────────────────────────────
        t0 = time.monotonic()
        cleaned = clean_document(parsed)
        clean_ms = int((time.monotonic() - t0) * 1000)
        logger.info("doc=%s clean=%dms blocks=%d", document_id, clean_ms, len(cleaned.blocks))

        # ── Chunk ──────────────────────────────────────────────────────
        t0 = time.monotonic()
        chunks = chunk_document(cleaned)
        chunk_ms = int((time.monotonic() - t0) * 1000)
        logger.info("doc=%s chunk=%dms chunks=%d", document_id, chunk_ms, len(chunks))

        # ── Persist chunks in one transaction ──────────────────────────
        # Delete any old chunks and vectors first (supports retry).
        db.query(Chunk).filter(Chunk.document_id == document_id).delete()
        delete_by_document(document_id)

        chunk_rows: list[Chunk] = []
        for c in chunks:
            row = Chunk(
                document_id=document_id,
                workspace_id=doc.workspace_id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                section_title=c.section_title,
                text=c.text,
                char_count=c.char_count,
            )
            db.add(row)
            chunk_rows.append(row)

        doc.status       = DocumentStatus.CHUNKED
        doc.page_count   = parsed.page_count
        doc.chunk_count  = len(chunks)
        doc.processed_at = _now()
        doc.updated_at   = _now()
        doc.error_message = None
        db.commit()
        # Refresh chunk rows to get their DB-assigned UUIDs.
        for row in chunk_rows:
            db.refresh(row)
        logger.info("doc=%s CHUNKED successfully.", document_id)

        # ── Embed ───────────────────────────────────────────────────────
        doc.status = DocumentStatus.INDEXING
        doc.updated_at = _now()
        db.commit()

        embed_texts = [
            _build_embed_text(doc.filename, row.section_title, row.text)
            for row in chunk_rows
        ]

        t0 = time.monotonic()
        dense_vecs = embedding_service.embed_documents(embed_texts)
        sparse_vecs = embedding_service.sparse_documents(embed_texts)
        embed_ms = int((time.monotonic() - t0) * 1000)
        logger.info("doc=%s embed=%dms chunks=%d", document_id, embed_ms, len(chunk_rows))

        # Sanity check: dimension must match config.
        if dense_vecs and len(dense_vecs[0]) != settings.EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(dense_vecs[0])}, "
                f"expected {settings.EMBEDDING_DIM}"
            )

        # ── Upsert into Qdrant ─────────────────────────────────────────
        ensure_collection()
        t0 = time.monotonic()
        upsert_chunks(chunk_rows, doc.filename, dense_vecs, sparse_vecs)
        upsert_ms = int((time.monotonic() - t0) * 1000)
        logger.info("doc=%s upsert=%dms", document_id, upsert_ms)

        doc.status     = DocumentStatus.COMPLETED
        doc.updated_at = _now()
        db.commit()
        logger.info("doc=%s COMPLETED. embed=%dms upsert=%dms", document_id, embed_ms, upsert_ms)

    except Exception as exc:
        db.rollback()
        short_msg = str(exc)[:500]
        try:
            doc = db.get(Document, document_id)
            if doc:
                doc.status = DocumentStatus.FAILED
                doc.error_message = short_msg
                doc.updated_at = _now()
                db.commit()
        except Exception:
            db.rollback()
        logger.error("doc=%s FAILED: %s", document_id, short_msg)
