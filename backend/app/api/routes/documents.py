"""
api/routes/documents.py — Document upload, listing, inspection, and deletion.

Workspace-scoped routes use require_workspace_member (non-members get 404).
Document-level routes resolve the workspace from the document and check membership.

POST   /api/workspaces/{workspace_id}/documents           — upload (202 + BackgroundTask)
GET    /api/workspaces/{workspace_id}/documents           — list
GET    /api/documents/{document_id}                       — get (member of workspace)
GET    /api/documents/{document_id}/chunks                — paginated chunks
DELETE /api/documents/{document_id}                       — owner or uploader only
POST   /api/documents/{document_id}/retry                 — only if FAILED
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException,
    Query, UploadFile, status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_workspace_member
from app.core.config import settings
from app.db.database import SessionLocal
from app.models.document import Chunk, Document, DocumentStatus
from app.models.user import User
from app.models.workspace import WorkspaceMember
from app.rag.ingestion import run_ingestion
from app.schemas.document import ChunkResponse, DocumentResponse
from app.services.storage_service import storage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])

# Allowed extensions and their magic-byte signatures
_ALLOWED_TYPES = {"pdf", "docx", "pptx"}
_MAGIC = {
    "pdf":  b"%PDF",
    "docx": b"PK\x03\x04",   # ZIP header
    "pptx": b"PK\x03\x04",   # ZIP header
}
_MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


# ── Helpers ────────────────────────────────────────────────────────────

def _extension(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read upload data, refusing to load more than max_bytes."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = file.file.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _get_doc_as_member(
    document_id: uuid.UUID,
    current_user: User,
    db: Session,
) -> Document:
    """Return the document if the current user is a member of its workspace, else 404."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == doc.workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
        .first()
    )
    if member is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


def _bg_ingest(document_id: uuid.UUID, file_path: str) -> None:
    """Background task: open its own DB session and run ingestion."""
    db = SessionLocal()
    try:
        run_ingestion(document_id, db, file_path)
    finally:
        db.close()


# ── Routes ─────────────────────────────────────────────────────────────

@router.post(
    "/workspaces/{workspace_id}/documents",
    response_model=DocumentResponse,
    status_code=202,
)
def upload_document(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    workspace_and_member: tuple = Depends(require_workspace_member),
    current_user: User = Depends(get_current_user),
):
    workspace, _ = workspace_and_member

    # --- Validation ---
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = _extension(file.filename)
    if ext not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '.{ext}'. Allowed: pdf, docx, pptx.",
        )

    data = _read_limited(file, _MAX_BYTES)

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Verify magic bytes
    magic = _MAGIC[ext]
    if not data[:len(magic)] == magic:
        raise HTTPException(
            status_code=400,
            detail="File content does not match the declared extension.",
        )

    # Compute sha256 for deduplication
    content_hash = hashlib.sha256(data).hexdigest()

    existing = (
        db.query(Document)
        .filter(
            Document.workspace_id == workspace_id,
            Document.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate file. Already uploaded as document id={existing.id}.",
        )

    # Sanitise filename for display: strip directory components
    safe_filename = Path(file.filename).name

    # Persist file (UUID name, NOT user filename)
    storage_path = storage.save(data, ext)
    full_path = str(storage.open(storage_path))

    doc = Document(
        workspace_id=workspace_id,
        uploaded_by=current_user.id,
        filename=safe_filename,
        file_type=ext,
        storage_path=storage_path,
        file_size=len(data),
        content_hash=content_hash,
        status=DocumentStatus.PENDING,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Kick off ingestion in the background
    background_tasks.add_task(_bg_ingest, doc.id, full_path)

    logger.info("Uploaded doc=%s workspace=%s file=%s", doc.id, workspace_id, safe_filename)
    return DocumentResponse.model_validate(doc)


@router.get("/workspaces/{workspace_id}/documents", response_model=list[DocumentResponse])
def list_documents(
    workspace_id: uuid.UUID,
    db: Session = Depends(get_db),
    workspace_and_member: tuple = Depends(require_workspace_member),
):
    docs = (
        db.query(Document)
        .filter(Document.workspace_id == workspace_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_doc_as_member(document_id, current_user, db)
    return DocumentResponse.model_validate(doc)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkResponse])
def list_chunks(
    document_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_doc_as_member(document_id, current_user, db)  # access check
    chunks = (
        db.query(Chunk)
        .filter(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [ChunkResponse.model_validate(c) for c in chunks]


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_doc_as_member(document_id, current_user, db)

    # Only the workspace owner OR the uploader may delete
    member = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.workspace_id == doc.workspace_id,
            WorkspaceMember.user_id == current_user.id,
        )
        .first()
    )
    is_owner    = member and member.role == "owner"
    is_uploader = doc.uploaded_by == current_user.id
    if not (is_owner or is_uploader):
        raise HTTPException(status_code=403, detail="Permission denied.")

    # Remove stored file first
    try:
        storage.delete(doc.storage_path)
    except Exception as e:
        logger.warning("Could not delete file %s: %s", doc.storage_path, e)

    db.delete(doc)
    db.commit()
    logger.info("Deleted doc=%s", document_id)


@router.post("/documents/{document_id}/retry", response_model=DocumentResponse, status_code=202)
def retry_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = _get_doc_as_member(document_id, current_user, db)
    if doc.status != DocumentStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail=f"Retry is only allowed for FAILED documents. Current status: {doc.status}.",
        )

    full_path = str(storage.open(doc.storage_path))
    doc.status = DocumentStatus.PENDING
    doc.error_message = None
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(_bg_ingest, doc.id, full_path)
    return DocumentResponse.model_validate(doc)
