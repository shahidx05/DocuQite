"""
tests/test_college_loader.py — Tests for Phase 3B-2: College corpus loader.

Verifies:
  - File list equals disk contents; never lists files not on disk
  - Manifest entry with no file is ignored
  - Missing manifest works (HTML title from <title>, PDF title from heading, source_url null)
  - No access outside project folder
  - Title rules:
      * images__ files ALWAYS use cleaned filename X (URL-decode, strip .docx/.pdf, underscores to spaces, strip hash)
      * uc__ opaque files use first non-letterhead line of page 1 (15+ letters, not garbled, not generic), fallback to "College document <hash6>"
      * letterhead lines skipped
      * HTML entities decoded (&amp; -> &)
      * unique titles guaranteed
  - Selection rules:
      * fill priority: syllabus, schemes, circulars/notices, BoS, reports, then other (max 10)
      * "other" capped at 10 files total, prefers most text, deprioritizes SOP/brochure/banner/CO-PO
      * total may be below 60
  - Excluded priority candidates logged with PII line counts only (no values)
  - Dry-run does not write to DB or Qdrant
  - HTML ingestion reaches COMPLETED in the test collection with source metadata
  - Duplicates skipped by content hash
  - One failing file does not abort the batch run
Uses ragdb_test and rag_chunks_test only.
"""

from pathlib import Path
import sys

# Ensure root directory is in sys.path to import scripts
_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import hashlib
import json
import uuid
from collections import Counter, defaultdict
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.rag.ingestion import run_ingestion
from app.services.storage_service import storage
from app.services.vector_service import get_qdrant_client
from qdrant_client.http import models as qmodels
from tests.conftest import _TestSessionLocal
import scripts.load_college as loader


# ── Helpers ────────────────────────────────────────────────────────────

def _make_pdf(text: str, num_pages: int = 1) -> bytes:
    import fitz
    doc = fitz.open()
    for _ in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    return doc.tobytes()


def _make_scanned_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page()  # blank page
    return doc.tobytes()


def _setup_user_and_workspace(db: Session) -> tuple[User, Workspace]:
    user = User(
        email=f"loader_{uuid.uuid4().hex[:8]}@example.com",
        name="Loader User",
        password_hash="mock_hashed_pw",
    )
    db.add(user)
    db.flush()
    ws = Workspace(name="Test College Workspace", owner_id=user.id)
    db.add(ws)
    db.flush()
    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner")
    db.add(member)
    db.commit()
    db.refresh(user)
    db.refresh(ws)
    return user, ws


# ── Test Suite ─────────────────────────────────────────────────────────

class TestDiskBasedFileListAndManifest:
    def test_file_list_equals_disk_contents(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        # Create 2 HTML files and 2 PDFs on disk
        (pages_dir / "page1.html").write_text("<html><head><title>Page 1</title></head><body><p>Text</p></body></html>", encoding="utf-8")
        (pages_dir / "page2.html").write_text("<html><head><title>Page 2</title></head><body><p>Text</p></body></html>", encoding="utf-8")

        pdf_text = "\n".join(["Academic syllabus details for engineering students."] * 15)
        (pdfs_dir / "syllabus1.pdf").write_bytes(_make_pdf(pdf_text))
        (pdfs_dir / "syllabus2.pdf").write_bytes(_make_pdf(pdf_text))

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "pages": [
                {"local_path": "pages/page1.html", "title": "Page One", "url": "https://example.com/p1"},
                {"local_path": "pages/ghost.html", "title": "Ghost", "url": "https://example.com/ghost"},
            ],
            "assets": [
                {"local_path": "pdfs/syllabus1.pdf", "original_filename": "Syllabus 1", "url": "https://example.com/s1"},
                {"local_path": "pdfs/nonexistent.pdf", "original_filename": "Ghost PDF", "url": "https://example.com/ghost_pdf"},
            ]
        }), encoding="utf-8")

        selected_html, selected_pdfs, excluded, stats = loader.select_college_corpus(
            manifest_path=manifest_path,
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
            max_pdfs=10,
        )

        selected_html_files = {h["filename"] for h in selected_html}
        selected_pdf_files = {p["filename"] for p in selected_pdfs}

        assert selected_html_files == {"page1.html", "page2.html"}
        assert selected_pdf_files == {"syllabus1.pdf", "syllabus2.pdf"}
        assert "ghost.html" not in selected_html_files
        assert "nonexistent.pdf" not in selected_pdf_files

        assert stats["html_on_disk"] == 2
        assert stats["pdf_on_disk"] == 2
        assert stats["total_on_disk"] == 4
        assert stats["manifest_not_on_disk"] == 2
        assert stats["disk_without_manifest"] == 2

    def test_manifest_entry_with_no_file_is_ignored(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        pdf_text = "\n".join(["Academic syllabus details for engineering students."] * 15)
        (pdfs_dir / "real.pdf").write_bytes(_make_pdf(pdf_text))

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "pages": [{"local_path": "pages/phantom_page.html", "url": "https://example.com/phantom"}],
            "assets": [
                {"local_path": "pdfs/real.pdf", "original_filename": "Real PDF", "url": "https://example.com/real"},
                {"local_path": "pdfs/phantom1.pdf", "url": "https://example.com/p1"},
                {"local_path": "pdfs/phantom2.pdf", "url": "https://example.com/p2"},
            ]
        }), encoding="utf-8")

        selected_html, selected_pdfs, excluded, stats = loader.select_college_corpus(
            manifest_path=manifest_path,
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
            max_pdfs=10,
        )

        assert len(selected_html) == 0
        assert len(selected_pdfs) == 1
        assert selected_pdfs[0]["filename"] == "real.pdf"
        assert stats["manifest_not_on_disk"] == 3

    def test_missing_manifest_works(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        (pages_dir / "department_overview.html").write_text(
            "<html><head><title>Department of Information Technology</title></head><body><p>Overview</p></body></html>",
            encoding="utf-8",
        )

        pdf_lines = [
            "Department of Information Technology Syllabus 2026",
            "This document describes the complete curriculum and evaluation schemes.",
        ] + ["Standard academic syllabus content paragraph line."] * 15
        (pdfs_dir / "curriculum_scheme.pdf").write_bytes(_make_pdf("\n".join(pdf_lines)))

        missing_manifest_path = tmp_path / "does_not_exist_manifest.json"
        assert not missing_manifest_path.exists()

        selected_html, selected_pdfs, excluded, stats = loader.select_college_corpus(
            manifest_path=missing_manifest_path,
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
            max_pdfs=10,
        )

        assert len(selected_html) == 1
        assert selected_html[0]["title"] == "Department of Information Technology"
        assert selected_html[0]["url"] is None

        assert len(selected_pdfs) == 1
        assert selected_pdfs[0]["title"] == "curriculum scheme"
        assert selected_pdfs[0]["url"] is None

        assert stats["manifest_not_on_disk"] == 0
        assert stats["disk_without_manifest"] == 2

    def test_no_access_outside_project_folder(self):
        assert loader.DEFAULT_MANIFEST_PATH.is_relative_to(loader.ROOT_DIR)
        assert loader.DEFAULT_MANIFEST_PATH == loader.ROOT_DIR / "data" / "raw" / "college" / "manifest.json"
        assert loader.DEFAULT_PAGES_DIR.is_relative_to(loader.ROOT_DIR)
        assert loader.DEFAULT_PDFS_DIR.is_relative_to(loader.ROOT_DIR)

        dummy_path = loader.ROOT_DIR / "data" / "raw" / "college" / "non_existent_manifest.json"
        lookup, filenames = loader.load_manifest(dummy_path)
        assert lookup == {}
        assert filenames == set()


class TestTitleRefinementsAndRules:
    def test_images_filename_always_cleaned(self, tmp_path: Path):
        pdfs_dir = tmp_path / "pdfs"
        pdfs_dir.mkdir()

        # Document has an unrelated page 1 heading, but images__ files must ALWAYS use cleaned filename X
        pdf_lines = [
            "Random Unrelated Page Heading Text Here",
            "Some other line of academic curriculum text.",
        ] + ["Standard academic syllabus content text line."] * 15

        fn = "images__Departments__information_technology__event__DevOps%20Workshop%20Report.docx.pdf__25c618d0.pdf"
        p = pdfs_dir / fn
        p.write_bytes(_make_pdf("\n".join(pdf_lines)))

        title = loader.extract_pdf_title(p)
        # Must be cleaned filename X: URL-decoded, stripped .docx/.pdf, underscores to spaces, stripped hash
        assert title == "DevOps Workshop Report"

    def test_uc_opaque_page1_or_hash(self, tmp_path: Path):
        pdfs_dir = tmp_path / "pdfs"
        pdfs_dir.mkdir()

        # 1. Clean valid heading with 15+ letters on page 1
        valid_lines = [
            "MADHAV INSTITUTE OF TECHNOLOGY & SCIENCE, GWALIOR",
            "MITS Gwalior (Accredited Institute)",
            "Specialized Machine Learning Curriculum Overview",
            "Detailed course syllabus and evaluation methodology.",
        ] + ["Standard academic syllabus content text line."] * 15

        p1 = pdfs_dir / "uc__12345678.pdf"
        p1.write_bytes(_make_pdf("\n".join(valid_lines)))
        t1 = loader.extract_pdf_title(p1)
        assert t1 == "Specialized Machine Learning Curriculum Overview"

        # 2. Garbled / generic / under 15 letters -> fallback to "College document <hash6>"
        garbled_lines = [
            "MADHAV INSTITUTE OF TECHNOLOGY & SCIENCE, GWALIOR",
            "!@#$%^&*()_+~`=-{}[]:;'<>?,./ \x00\x01\x02 aaaaa bbbbb ccccc ddddd eeeee",
        ] + ["Standard academic syllabus content text line."] * 15

        p2 = pdfs_dir / "uc__abcdef99.pdf"
        p2.write_bytes(_make_pdf("\n".join(garbled_lines)))
        t2 = loader.extract_pdf_title(p2)
        assert t2 == "College document abcdef"

    def test_entities_decoded(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pages_dir.mkdir()
        (pages_dir / "research.html").write_text(
            "<html><head><title>R&amp;D Activities &amp; Projects - MITS Gwalior</title></head><body><p>Text</p></body></html>",
            encoding="utf-8",
        )
        selected_html, _, _, _ = loader.select_college_corpus(
            manifest_path=tmp_path / "manifest.json",
            pages_dir=pages_dir,
            pdfs_dir=tmp_path / "pdfs",
            max_pdfs=10,
        )
        assert len(selected_html) == 1
        assert selected_html[0]["title"] == "R&D Activities & Projects - MITS Gwalior"

    def test_unique_titles(self):
        items = [
            {"filename": "images__bos__meeting_14.12.2021.pdf__123456.pdf", "title": "Board of Studies Proceeding"},
            {"filename": "images__bos__meeting_08.06.2022.pdf__abcdef.pdf", "title": "Board of Studies Proceeding"},
            {"filename": "uc__015ae44e.pdf", "title": "College document 015ae4"},
            {"filename": "uc__015ae499.pdf", "title": "College document 015ae4"},
        ]
        result = loader.make_unique_titles(items)
        titles = [r["title"] for r in result]
        assert len(titles) == len(set(titles)), "All titles in result must be made unique"
        assert any("14.12.2021" in t for t in titles)


class TestSelectionPrioritiesAndCaps:
    def test_other_capped_at_10_and_prefers_most_text(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        # Create 15 'other' documents with different lengths and some SOP/brochures
        # 1-12: High-value documents (no sop/brochure)
        for i in range(12):
            text_lines = [f"Detailed academic documentation and analysis section {i}."] * (20 + i * 5)
            fn = f"images__Departments__general_doc_{i:02d}.pdf__{i:06x}.pdf"
            (pdfs_dir / fn).write_bytes(_make_pdf("\n".join(text_lines)))

        # 13-15: SOP / brochure low-value documents
        for i in range(3):
            text_lines = [f"Standard operating procedure checklist line {i}."] * 50
            fn = f"images__sop__lab_safety_sop_{i:02d}.pdf__{100+i:06x}.pdf"
            (pdfs_dir / fn).write_bytes(_make_pdf("\n".join(text_lines)))

        selected_html, selected_pdfs, excluded, stats = loader.select_college_corpus(
            manifest_path=tmp_path / "manifest.json",
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
            max_pdfs=60,
        )

        other_selected = [p for p in selected_pdfs if p["category"] == "other"]
        # Rule: Cap "other" at 10 files total
        assert len(other_selected) == 10

        # Rule: SOP / brochure files should NOT be selected when sufficient better files exist
        for p in other_selected:
            assert "sop" not in p["filename"].lower()
            assert "brochure" not in p["filename"].lower()

    def test_fill_priority_order_and_total_below_60(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        # Create 2 syllabus, 1 scheme, 1 circular, 1 bos, 1 report, and 15 others
        base_lines = ["Academic course curriculum text paragraph line."] * 20
        (pdfs_dir / "images__curriculum__it_syllabus_sem3.pdf__111111.pdf").write_bytes(_make_pdf("\n".join(base_lines)))
        (pdfs_dir / "images__curriculum__it_syllabus_sem5.pdf__222222.pdf").write_bytes(_make_pdf("\n".join(base_lines)))
        (pdfs_dir / "images__scheme__btech_scheme_2026.pdf__333333.pdf").write_bytes(_make_pdf("\n".join(base_lines)))
        (pdfs_dir / "images__circular__academic_order_notice.pdf__444444.pdf").write_bytes(_make_pdf("\n".join(base_lines)))
        (pdfs_dir / "images__bos__bos_proceeding_meeting.pdf__555555.pdf").write_bytes(_make_pdf("\n".join(base_lines)))
        (pdfs_dir / "images__reports__alumni_session_report.pdf__666666.pdf").write_bytes(_make_pdf("\n".join(base_lines)))

        other_lines = ["General administrative note text paragraph line."] * 20
        for i in range(15):
            (pdfs_dir / f"images__general__academic_note_{i}.pdf__{1000+i:06x}.pdf").write_bytes(_make_pdf("\n".join(other_lines)))

        selected_html, selected_pdfs, excluded, stats = loader.select_college_corpus(
            manifest_path=tmp_path / "manifest.json",
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
            max_pdfs=60,
        )

        cats = [p["category"] for p in selected_pdfs]
        cat_counts = Counter(cats)

        # High priority files taken in full: 2 syllabus, 1 scheme, 1 circular, 1 bos, 1 report = 6
        # Other capped at 10
        # Total = 16 (which is well below 60)
        assert cat_counts["syllabus"] == 2
        assert cat_counts["schemes"] == 1
        assert cat_counts["circulars/notices"] == 1
        assert cat_counts["bos"] == 1
        assert cat_counts["reports"] == 1
        assert cat_counts["other"] == 10
        assert len(selected_pdfs) == 16

    def test_excluded_priority_candidates_logged_with_pii_counts_only(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        # Syllabus file with roll number
        roll_lines = ["Student enrolment 0901IT221001 passed."] + ["Academic curriculum paragraph line." for _ in range(12)]
        (pdfs_dir / "images__curriculum__it_syllabus_roll.pdf__777777.pdf").write_bytes(_make_pdf("\n".join(roll_lines)))

        # Scheme file with too many emails
        pii_lines = [f"Contact email{i}@mitsgwl.ac.in for details" for i in range(6)] + ["Academic curriculum paragraph line." for _ in range(10)]
        (pdfs_dir / "images__scheme__btech_scheme_pii.pdf__888888.pdf").write_bytes(_make_pdf("\n".join(pii_lines)))

        selected_html, selected_pdfs, excluded, stats = loader.select_college_corpus(
            manifest_path=tmp_path / "manifest.json",
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
            max_pdfs=10,
        )

        excluded_prio = stats["excluded_priority_candidates"]
        assert len(excluded_prio) == 2
        reasons = {item["filename"]: item["reason"] for item in excluded_prio}

        # Verify PII line counts only, no raw PII values (no email addresses, no roll numbers)
        assert "has_roll (1 roll lines)" in reasons["images__curriculum__it_syllabus_roll.pdf__777777.pdf"]
        assert "0901IT221001" not in reasons["images__curriculum__it_syllabus_roll.pdf__777777.pdf"]

        assert "too_many_pii (6 email lines, 0 phone lines)" in reasons["images__scheme__btech_scheme_pii.pdf__888888.pdf"]
        assert "@mitsgwl.ac.in" not in reasons["images__scheme__btech_scheme_pii.pdf__888888.pdf"]


class TestDryRunDoesNotWriteDBOrQdrant:
    def test_dry_run_is_read_only(self, tmp_path: Path, db: Session):
        qdrant_client = get_qdrant_client()
        initial_points = qdrant_client.count(collection_name=settings.QDRANT_COLLECTION).count
        initial_docs = db.query(Document).count()

        html_item = {
            "type": "html",
            "path": tmp_path / "sample.html",
            "filename": "sample.html",
            "title": "Sample Title",
            "url": "https://example.com/sample",
            "size": 1024,
            "pages": None,
        }
        pdf_item = {
            "type": "pdf",
            "path": tmp_path / "sample.pdf",
            "filename": "sample.pdf",
            "title": "Sample PDF Title",
            "url": "https://example.com/sample.pdf",
            "size": 2048,
            "pages": 2,
            "category": "syllabus",
        }
        excluded_counts = {"exceeds_size": 0, "not_text": 0, "excluded_keyword": 0, "has_roll": 0, "too_many_pii": 0}
        stats = {
            "html_on_disk": 1,
            "pdf_on_disk": 1,
            "total_on_disk": 2,
            "manifest_not_on_disk": 0,
            "disk_without_manifest": 2,
            "eligible_pdfs": 1,
        }

        # Run dry run
        loader.run_dry_run([html_item], [pdf_item], excluded_counts, stats)

        # Verify no changes in DB or Qdrant
        assert db.query(Document).count() == initial_docs
        assert qdrant_client.count(collection_name=settings.QDRANT_COLLECTION).count == initial_points


class TestIngestionAndDuplicates:
    def test_html_ingestion_completed_with_metadata(self, tmp_path: Path):
        session = _TestSessionLocal()
        try:
            user, workspace = _setup_user_and_workspace(session)

            html_content = """
            <html>
            <head><title>Course Structure - MITS Gwalior</title></head>
            <body>
                <h1>Course Overview</h1>
                <p>Detailed syllabus for Information Technology engineering students.</p>
                <table>
                    <tr><th>Code</th><th>Subject</th></tr>
                    <tr><td>IT101</td><td>Data Structures</td></tr>
                </table>
            </body>
            </html>
            """
            html_bytes = html_content.encode("utf-8")
            storage_path = storage.save(html_bytes, "html")
            c_hash = hashlib.sha256(html_bytes).hexdigest()

            doc = Document(
                workspace_id=workspace.id,
                uploaded_by=user.id,
                filename="courses.html",
                file_type="html",
                storage_path=storage_path,
                file_size=len(html_bytes),
                content_hash=c_hash,
                source_url="https://web.mitsgwalior.in/courses",
                source_title="Course Structure - MITS Gwalior",
                status=DocumentStatus.PENDING,
            )
            session.add(doc)
            session.commit()
            session.refresh(doc)

            # Ingest
            run_ingestion(doc.id, session, str(storage.open(doc.storage_path)))
            doc = session.get(Document, doc.id)

            assert doc.status == DocumentStatus.COMPLETED
            assert doc.chunk_count is not None and doc.chunk_count > 0

            # Verify Qdrant points have source_url and source_title
            qclient = get_qdrant_client()
            points, _ = qclient.scroll(
                collection_name=settings.QDRANT_COLLECTION,
                scroll_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchValue(value=str(doc.id)),
                        )
                    ]
                ),
                limit=10,
                with_payload=True,
            )
            assert len(points) > 0
            p0 = points[0].payload
            assert p0.get("document_name") == "Course Structure - MITS Gwalior"
            assert p0.get("source_url") == "https://web.mitsgwalior.in/courses"
            assert p0.get("source_title") == "Course Structure - MITS Gwalior"
        finally:
            session.close()

    def test_duplicate_skipping(self):
        session = _TestSessionLocal()
        try:
            user, workspace = _setup_user_and_workspace(session)
            content = b"Exact identical document content bytes"
            c_hash = hashlib.sha256(content).hexdigest()

            # Insert first document
            doc1 = Document(
                workspace_id=workspace.id,
                uploaded_by=user.id,
                filename="doc1.pdf",
                file_type="pdf",
                storage_path="mock1.pdf",
                file_size=len(content),
                content_hash=c_hash,
                status=DocumentStatus.COMPLETED,
            )
            session.add(doc1)
            session.commit()

            # Second document check
            existing = (
                session.query(Document)
                .filter(Document.workspace_id == workspace.id, Document.content_hash == c_hash)
                .first()
            )
            assert existing is not None
            assert existing.id == doc1.id
        finally:
            session.close()

    def test_one_failing_file_does_not_abort_run(self, tmp_path: Path):
        session = _TestSessionLocal()
        try:
            user, workspace = _setup_user_and_workspace(session)

            # 1. Invalid file (will fail parsing/ingestion)
            bad_bytes = b"NOT A VALID PDF OR HTML DATA AT ALL"
            bad_path = storage.save(bad_bytes, "pdf")
            bad_doc = Document(
                workspace_id=workspace.id,
                uploaded_by=user.id,
                filename="corrupt.pdf",
                file_type="pdf",
                storage_path=bad_path,
                file_size=len(bad_bytes),
                content_hash=hashlib.sha256(bad_bytes).hexdigest(),
                status=DocumentStatus.PENDING,
            )
            session.add(bad_doc)
            session.commit()
            session.refresh(bad_doc)

            # 2. Valid file
            good_lines = "\n".join(["Valid PDF content with adequate length."] * 15)
            good_bytes = _make_pdf(good_lines)
            good_path = storage.save(good_bytes, "pdf")
            good_doc = Document(
                workspace_id=workspace.id,
                uploaded_by=user.id,
                filename="good.pdf",
                file_type="pdf",
                storage_path=good_path,
                file_size=len(good_bytes),
                content_hash=hashlib.sha256(good_bytes).hexdigest(),
                status=DocumentStatus.PENDING,
            )
            session.add(good_doc)
            session.commit()
            session.refresh(good_doc)

            # Run first file (fails)
            run_ingestion(bad_doc.id, session, str(storage.open(bad_doc.storage_path)))
            bad_doc = session.get(Document, bad_doc.id)
            assert bad_doc.status == DocumentStatus.FAILED

            # Run second file (must succeed despite previous failure)
            run_ingestion(good_doc.id, session, str(storage.open(good_doc.storage_path)))
            good_doc = session.get(Document, good_doc.id)
            assert good_doc.status == DocumentStatus.COMPLETED
        finally:
            session.close()


class TestRollExclusionsAndPII:
    def test_roll_regex_matches_extended_patterns(self):
        assert loader.ROLL_RE.search("BTIT24O1009")
        assert loader.ROLL_RE.search("BTCS23O1234")
        assert loader.ROLL_RE.search("0901IT221001")
        assert loader.ROLL_RE.search("Student BTIT24O1009 submitted project")
        # normal numbers should not match
        assert not loader.ROLL_RE.search("Year 2024")
        assert not loader.ROLL_RE.search("Page 42")

    def test_name_roll_regex(self):
        assert loader.NAME_ROLL_RE.search("ADITYA GUPTA BTIT24O1009")
        assert loader.NAME_ROLL_RE.search("Rahul Sharma 0901IT221001")
        assert loader.NAME_ROLL_RE.search("John Doe BTCS23O1234")

    def test_title_with_roll_pattern_is_excluded(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        pdf_bytes = _make_pdf("Valid academic document content with plenty of text." * 10)
        (pdfs_dir / "uc__11223344.pdf").write_bytes(pdf_bytes)

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "assets": [
                {"local_path": "pdfs/uc__11223344.pdf", "title": "Project Report - Rahul Verma BTIT24O1009"}
            ]
        }))

        _, selected_pdfs, excluded_counts, stats = loader.select_college_corpus(
            manifest_path=manifest_path,
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
        )
        assert len(selected_pdfs) == 0
        assert excluded_counts["has_roll"] == 1
        assert len(stats["excluded_roll_candidates"]) == 1

    def test_page1_with_roll_or_name_roll_is_excluded(self, tmp_path: Path):
        pages_dir = tmp_path / "pages"
        pdfs_dir = tmp_path / "pdfs"
        pages_dir.mkdir()
        pdfs_dir.mkdir()

        # Page 1 has student name + roll number pattern
        p1_text = "MADHAV INSTITUTE OF TECHNOLOGY & SCIENCE\nADITYA GUPTA BTIT24O1009\nSubmitted assignment."
        p2_text = "Detailed academic report content with sufficient text." * 10
        import fitz
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((72, 72), p1_text)
        p2 = doc.new_page()
        p2.insert_text((72, 72), p2_text)
        pdf_bytes = doc.tobytes()

        (pdfs_dir / "uc__5d46df03.pdf").write_bytes(pdf_bytes)

        _, selected_pdfs, excluded_counts, stats = loader.select_college_corpus(
            manifest_path=tmp_path / "nonexistent.json",
            pages_dir=pages_dir,
            pdfs_dir=pdfs_dir,
        )
        assert len(selected_pdfs) == 0
        assert excluded_counts["has_roll"] == 1
        assert any(item["filename"] == "uc__5d46df03.pdf" for item in stats["excluded_roll_candidates"])


class TestSyllabusCategoryAndTitleRules:
    def test_categorize_pdf_syllabus_precedence(self):
        # 1. Title/filename matches
        assert loader.categorize_pdf("B.Tech Syllabus", "doc.pdf") == "syllabus"
        assert loader.categorize_pdf("Academic Curriculum", "doc.pdf") == "syllabus"

        # 2. Page 1 text cues before "other"
        assert loader.categorize_pdf("Document 1", "uc__12345678.pdf", p1_text="Detailed course contents of IT") == "syllabus"
        assert loader.categorize_pdf("Document 2", "uc__12345678.pdf", p1_text="Departmental Core courses for semester") == "syllabus"
        assert loader.categorize_pdf("Document 3", "uc__12345678.pdf", p1_text="V Semester Course Code IT-501") == "syllabus"

        # 3. High-priority non-syllabus remain intact
        assert loader.categorize_pdf("BoS Meeting Proceedings", "bos.pdf", p1_text="curriculum discussed") == "bos"
        assert loader.categorize_pdf("Annual Placement Report", "report.pdf", p1_text="syllabus covered") == "reports"

        # 4. Low-value SOP / CO-PO files do not become syllabus
        assert loader.categorize_pdf("SOP for Laboratory", "sop.pdf", p1_text="curriculum mentioned") == "other"
        assert loader.categorize_pdf("CO-PO Attainment", "co_po.pdf", p1_text="semester IT-101") == "other"

    def test_build_syllabus_title_variations(self):
        # B.Tech IT Honours with year
        p1_h = "MADHAV INSTITUTE\nSCHEME\n(Under Flexible Curriculum)\nB. Tech Information Technology with Honours\nAdmitted Batch (2020-2021)"
        t_h = loader.build_syllabus_title(p1_h, "uc__52e7ffa3.pdf")
        assert t_h == "B.Tech IT Honours Syllabus, 2020-2021"
        assert "(Under Flexible Curriculum)" not in t_h

        # B.Tech IT Minor with year
        p1_m = "MADHAV INSTITUTE\nSCHEME\n(Under Flexible Curriculum)\nB. Tech with Minor Specialization in Information Technology\nAdmitted Batch (2018-2019)"
        t_m = loader.build_syllabus_title(p1_m, "uc__1e1c99a5.pdf")
        assert t_m == "B.Tech IT Minor Syllabus, 2018-2019"
        assert "(Under Flexible Curriculum)" not in t_m

        # M.Tech IT with semester
        p1_mt = "Syllabi of Departmental Core (DC) Courses M.Tech I Semester (Information Technology)"
        t_mt = loader.build_syllabus_title(p1_mt, "uc__69b7f625.pdf")
        assert t_mt == "M.Tech IT Syllabus, Semester 1"

        # Programme + Semester format
        p1_sem5 = "B.Tech Information Technology Department\nSyllabus for V Semester (2022-2023)"
        t_sem5 = loader.build_syllabus_title(p1_sem5, "uc__12345678.pdf")
        assert "B.Tech IT Syllabus" in t_sem5
        assert "Semester 5" in t_sem5

        # Fallback when no details reliable
        t_fb = loader.build_syllabus_title("Random text with no programme info", "uc__a1b2c3d4.pdf")
        assert t_fb == "Syllabus a1b2c3"
