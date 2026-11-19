"""
services/storage_service.py — Thin storage abstraction.

LocalStorage writes files under UPLOAD_DIR using a UUID filename so user-supplied
filenames never touch the filesystem (path-traversal safety).

The interface is kept minimal so a GCS or S3 implementation can be dropped in later
without changing the upload route.
"""

import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import settings


class StorageService(Protocol):
    """Interface that every storage backend must satisfy."""

    def save(self, data: bytes | BinaryIO, extension: str) -> str:
        """Persist *data* and return the storage_path string."""
        ...

    def open(self, storage_path: str) -> Path:
        """Return a local Path object for the stored file."""
        ...

    def delete(self, storage_path: str) -> None:
        """Delete the stored file (silently ignore if already missing)."""
        ...


class LocalStorage:
    """Stores files in UPLOAD_DIR under a UUID filename."""

    def __init__(self, upload_dir: str | None = None):
        self._base = Path(upload_dir or settings.UPLOAD_DIR)
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes | BinaryIO, extension: str) -> str:
        filename = f"{uuid.uuid4().hex}.{extension}"
        dest = self._base / filename
        if isinstance(data, bytes):
            dest.write_bytes(data)
        else:
            dest.write_bytes(data.read())
        return filename  # relative to UPLOAD_DIR

    def open(self, storage_path: str) -> Path:
        return self._base / storage_path

    def delete(self, storage_path: str) -> None:
        target = self._base / storage_path
        target.unlink(missing_ok=True)


# Default singleton used by the application.
storage = LocalStorage()
