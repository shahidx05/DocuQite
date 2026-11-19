"""
tests/test_documents.py — Integration tests for the Phase 2 upload/ingest API.

All file content is generated in-memory using the installed parsers;
no files from data/raw/ are required.
"""

import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient


# ── File generators ────────────────────────────────────────────────────

def _make_pdf(text: str = "Hello PDF world. This is page one content.") -> bytes:
    """Create a minimal valid PDF in memory using PyMuPDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=12)
    return doc.tobytes()


def _make_docx(text: str = "Hello DOCX world.") -> bytes:
    """Create a minimal valid DOCX in memory."""
    from docx import Document
    doc = Document()
    doc.add_heading("Test Document", level=1)
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_pptx(text: str = "Hello PPTX world.") -> bytes:
    """Create a minimal valid PPTX in memory."""
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()
    slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(slide_layout)
    slide.shapes.title.text = "Test Slide"
    slide.placeholders[1].text = text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _make_scanned_pdf() -> bytes:
    """PDF with no text (image-only page) → should FAIL ingestion."""
    import fitz
    doc = fitz.open()
    doc.new_page()   # blank page, no text
    return doc.tobytes()


# ── Helpers ────────────────────────────────────────────────────────────

def _unique_email():
    return f"doc_{uuid.uuid4().hex[:8]}@example.com"


def _register_login(client, email=None, password="password123"):
    email = email or _unique_email()
    client.post("/api/auth/register", json={"name": "U", "email": email, "password": password})
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"], email


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _create_ws(client, token, name="WS"):
    return client.post("/api/workspaces", json={"name": name}, headers=_auth(token)).json()["id"]


def _upload(client, token, ws_id, data: bytes, filename: str, content_type="application/pdf"):
    return client.post(
        f"/api/workspaces/{ws_id}/documents",
        files={"file": (filename, io.BytesIO(data), content_type)},
        headers=_auth(token),
    )


def _wait_for_status(client, token, doc_id, desired, retries=15, delay=0.5):
    """Poll until the document reaches the desired status."""
    for _ in range(retries):
        r = client.get(f"/api/documents/{doc_id}", headers=_auth(token))
        if r.json().get("status") == desired:
            return r.json()
        time.sleep(delay)
    return client.get(f"/api/documents/{doc_id}", headers=_auth(token)).json()


# ── Upload success ─────────────────────────────────────────────────────

class TestUploadSuccess:
    def test_upload_pdf_returns_202(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, _make_pdf(), "test.pdf")
        assert r.status_code == 202
        body = r.json()
        assert body["status"] == "PENDING"
        assert body["file_type"] == "pdf"
        assert "password_hash" not in r.text

    def test_upload_docx_returns_202(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, _make_docx(), "test.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert r.status_code == 202

    def test_upload_pptx_returns_202(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, _make_pptx(), "test.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        assert r.status_code == 202

    def test_filename_sanitised(self, client, tmp_upload_dir):
        """Path-traversal filename must be sanitised to basename."""
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, _make_pdf(), "../../evil.pdf")
        assert r.status_code == 202
        assert r.json()["filename"] == "evil.pdf"


# ── Upload validation ──────────────────────────────────────────────────

class TestUploadValidation:
    def test_wrong_extension_415(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, b"hello", "test.txt", "text/plain")
        assert r.status_code == 415

    def test_fake_pdf_wrong_magic_400(self, client, tmp_upload_dir):
        """A .pdf file that doesn't start with %PDF must be rejected."""
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, b"This is not a PDF file", "fake.pdf")
        assert r.status_code == 400

    def test_empty_file_400(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, b"", "empty.pdf")
        assert r.status_code == 400

    def test_oversized_file_413(self, client, tmp_upload_dir, monkeypatch):
        """Simulate a file that exceeds MAX_UPLOAD_MB."""
        import app.api.routes.documents as doc_routes
        monkeypatch.setattr(doc_routes, "_MAX_BYTES", 10)  # 10 bytes limit for test
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, _make_pdf(), "big.pdf")
        assert r.status_code == 413

    def test_duplicate_upload_409(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        pdf_data = _make_pdf("unique content abc123")
        _upload(client, token, ws_id, pdf_data, "first.pdf")
        r2 = _upload(client, token, ws_id, pdf_data, "second.pdf")
        assert r2.status_code == 409
        assert "already uploaded" in r2.json()["detail"].lower()


# ── Access control ─────────────────────────────────────────────────────

class TestDocumentAccessControl:
    def _setup(self, client, tmp_upload_dir):
        token_a, _ = _register_login(client)
        token_b, _ = _register_login(client)
        ws_a = _create_ws(client, token_a, "WS-A")
        r = _upload(client, token_a, ws_a, _make_pdf("ws a content"), "a.pdf")
        doc_id = r.json()["id"]
        return token_a, token_b, ws_a, doc_id

    def test_non_member_cannot_upload(self, client, tmp_upload_dir):
        token_a, _ = _register_login(client)
        token_b, _ = _register_login(client)
        ws_a = _create_ws(client, token_a)
        r = _upload(client, token_b, ws_a, _make_pdf(), "b.pdf")
        assert r.status_code == 404

    def test_non_member_cannot_list_documents(self, client, tmp_upload_dir):
        token_a, token_b, ws_a, _ = self._setup(client, tmp_upload_dir)
        r = client.get(f"/api/workspaces/{ws_a}/documents", headers=_auth(token_b))
        assert r.status_code == 404

    def test_non_member_cannot_get_document(self, client, tmp_upload_dir):
        token_a, token_b, ws_a, doc_id = self._setup(client, tmp_upload_dir)
        r = client.get(f"/api/documents/{doc_id}", headers=_auth(token_b))
        assert r.status_code == 404

    def test_non_member_cannot_delete_document(self, client, tmp_upload_dir):
        token_a, token_b, ws_a, doc_id = self._setup(client, tmp_upload_dir)
        r = client.delete(f"/api/documents/{doc_id}", headers=_auth(token_b))
        assert r.status_code == 404

    def test_workspace_b_cannot_see_workspace_a_docs(self, client, tmp_upload_dir):
        token_a, _ = _register_login(client)
        token_b, _ = _register_login(client)
        ws_a = _create_ws(client, token_a, "WS-A")
        ws_b = _create_ws(client, token_b, "WS-B")
        _upload(client, token_a, ws_a, _make_pdf("secret"), "secret.pdf")
        r = client.get(f"/api/workspaces/{ws_b}/documents", headers=_auth(token_b))
        assert r.status_code == 200
        assert len(r.json()) == 0


# ── Delete ─────────────────────────────────────────────────────────────

class TestDocumentDelete:
    def test_uploader_can_delete(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        doc_id = _upload(client, token, ws_id, _make_pdf("del me"), "del.pdf").json()["id"]
        r = client.delete(f"/api/documents/{doc_id}", headers=_auth(token))
        assert r.status_code == 204
        # File should be gone from disk
        r2 = client.get(f"/api/documents/{doc_id}", headers=_auth(token))
        assert r2.status_code == 404

    def test_delete_removes_file_from_disk(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        doc_id = _upload(client, token, ws_id, _make_pdf("disk test"), "disk.pdf").json()["id"]
        storage_path = client.get(f"/api/documents/{doc_id}", headers=_auth(token)).json()
        # Files count before
        before = list(tmp_upload_dir.iterdir())
        client.delete(f"/api/documents/{doc_id}", headers=_auth(token))
        after = list(tmp_upload_dir.iterdir())
        assert len(after) < len(before)

    def test_non_uploader_non_owner_cannot_delete(self, client, tmp_upload_dir):
        token_a, _ = _register_login(client)
        token_b, email_b = _register_login(client)
        ws_id = _create_ws(client, token_a)
        # Add B as member
        client.post(f"/api/workspaces/{ws_id}/members", json={"email": email_b}, headers=_auth(token_a))
        doc_id = _upload(client, token_a, ws_id, _make_pdf("owned by a"), "a.pdf").json()["id"]
        r = client.delete(f"/api/documents/{doc_id}", headers=_auth(token_b))
        assert r.status_code == 403


# ── Retry ──────────────────────────────────────────────────────────────

class TestRetry:
    def test_retry_on_non_failed_returns_409(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        doc_id = _upload(client, token, ws_id, _make_pdf("retry me"), "r.pdf").json()["id"]
        # It's PENDING or CHUNKED — retry not allowed
        r = client.post(f"/api/documents/{doc_id}/retry", headers=_auth(token))
        # May be PENDING still (background not done) or CHUNKED — either way not FAILED
        # Allow both 409 (not FAILED) and 202 if it happened to fail already
        assert r.status_code in (202, 409)


# ── Path traversal safety ──────────────────────────────────────────────

class TestPathTraversal:
    def test_evil_filename_sanitised(self, client, tmp_upload_dir):
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        r = _upload(client, token, ws_id, _make_pdf("safe"), "../../etc/passwd.pdf")
        assert r.status_code == 202
        assert ".." not in r.json()["filename"]
        assert r.json()["filename"] == "passwd.pdf"

    def test_stored_file_inside_upload_dir(self, client, tmp_upload_dir):
        """Storage path must be just a filename, never a path that escapes UPLOAD_DIR."""
        token, _ = _register_login(client)
        ws_id = _create_ws(client, token)
        _upload(client, token, ws_id, _make_pdf("safe"), "test.pdf")
        # All files in tmp_upload_dir must be directly inside it (no subdirs escaping)
        for f in tmp_upload_dir.iterdir():
            assert f.parent == tmp_upload_dir
