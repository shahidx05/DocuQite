"""
rag/ingestion.py — Full ingestion pipeline: parse → clean → chunk → persist.

State machine:
  PENDING → PROCESSING → (parse → clean → chunk → DB write) → CHUNKED
                                                             → FAILED (on any error)

Retry: deletes old chunks first, then reruns from PENDING.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.document import Chunk, Document, DocumentStatus
from app.rag.chunking import chunk_document
from app.rag.cleaning import clean_document
from app.rag.parsing import parse_document

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_ingestion(document_id: uuid.UUID, db: Session, storage_path: str) -> None:
    """
    Entry point called by the BackgroundTask.
    Fetches the Document row, runs the pipeline, and writes the result back.
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
        # Delete any old chunks first (supports retry).
        db.query(Chunk).filter(Chunk.document_id == document_id).delete()

        for c in chunks:
            db.add(Chunk(
                document_id=document_id,
                workspace_id=doc.workspace_id,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                section_title=c.section_title,
                text=c.text,
                char_count=c.char_count,
            ))

        doc.status      = DocumentStatus.CHUNKED
        doc.page_count  = parsed.page_count
        doc.chunk_count = len(chunks)
        doc.processed_at = _now()
        doc.updated_at   = _now()
        doc.error_message = None
        db.commit()
        logger.info("doc=%s CHUNKED successfully.", document_id)

    except Exception as exc:
        db.rollback()
        # Store a short, non-stack-trace error message.
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
