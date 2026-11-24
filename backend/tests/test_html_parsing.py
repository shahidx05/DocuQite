"""
tests/test_html_parsing.py — Unit tests for Phase 3B-1:
  - HTML parsing (skipping ignored tags, section titles from h1-h4, table rows, title)
  - Cross-document boilerplate removal (40% threshold, <5 docs guard, unique kept)
  - PII redaction (email, phone, roll numbers; normal numbers untouched)
"""

from pathlib import Path
import pytest

from app.rag.cleaning import (
    CROSS_DOCUMENT_BOILERPLATE_THRESHOLD,
    MIN_CORPUS_SIZE_FOR_BOILERPLATE,
    clean_document,
    redact_pii,
    remove_cross_document_boilerplate,
)
from app.rag.parsing import (
    ParsedBlock,
    ParsedDocument,
    parse_document,
    parse_html,
)


# ── Test HTML Parsing ──────────────────────────────────────────────────

class TestHTMLParsing:
    def test_skips_ignored_tags_and_keeps_content(self, tmp_path: Path):
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Page Title</title>
            <style>body { color: red; }</style>
            <script>console.log("secret script");</script>
        </head>
        <body>
            <header><p>Header to drop</p></header>
            <nav><a href="#">Nav link to drop</a></nav>
            <aside><p>Sidebar to drop</p></aside>
            <form action="/"><input type="text" value="Form drop"></form>
            <noscript>Noscript drop</noscript>
            <svg><text>SVG drop</text></svg>

            <h1>Main Heading</h1>
            <p>This is genuine content in the body.</p>
            <p>Second paragraph with <b>bold</b> and <i>italic</i> formatting.</p>

            <footer>Footer to drop</footer>
        </body>
        </html>
        """
        p = tmp_path / "test.html"
        p.write_text(html_content, encoding="utf-8")

        doc = parse_html(p)
        assert doc.title == "Test Page Title"

        all_text = "\n".join(b.text for b in doc.blocks)
        # Verify ignored tags dropped
        assert "Header to drop" not in all_text
        assert "Nav link to drop" not in all_text
        assert "Sidebar to drop" not in all_text
        assert "Form drop" not in all_text
        assert "Noscript drop" not in all_text
        assert "SVG drop" not in all_text
        assert "Footer to drop" not in all_text
        assert "secret script" not in all_text

        # Verify genuine content kept
        assert "Main Heading" in all_text
        assert "This is genuine content in the body." in all_text
        assert "Second paragraph with bold and italic formatting." in all_text

    def test_headings_become_section_titles_and_page_number_is_none(self, tmp_path: Path):
        html_content = """
        <html>
        <head><title>Headings Test</title></head>
        <body>
            <p>Introduction before headings.</p>
            <h1>Chapter 1: Foundations</h1>
            <p>Paragraph under chapter 1.</p>
            <h2>Section 1.1: Basics</h2>
            <p>Paragraph under section 1.1.</p>
            <h3>Subsection 1.1.1</h3>
            <p>Paragraph under subsection.</p>
            <h4>Minor Header</h4>
            <p>Deep paragraph.</p>
        </body>
        </html>
        """
        p = tmp_path / "headings.html"
        p.write_text(html_content, encoding="utf-8")

        doc = parse_html(p)
        assert doc.title == "Headings Test"

        # Check page_number is None on all blocks
        for b in doc.blocks:
            assert b.page_number is None

        sections = [b.section_title for b in doc.blocks]
        assert None in sections  # introductory paragraph before first heading
        assert "Chapter 1: Foundations" in sections
        assert "Section 1.1: Basics" in sections
        assert "Subsection 1.1.1" in sections
        assert "Minor Header" in sections

    def test_table_rows_formatted_with_pipe(self, tmp_path: Path):
        html_content = """
        <html>
        <head><title>Table Test</title></head>
        <body>
            <h2>Faculty Table</h2>
            <table>
                <tr>
                    <th>S.No.</th>
                    <th>Name</th>
                    <th>Department</th>
                </tr>
                <tr>
                    <td>1</td>
                    <td>Dr. Akhilesh Tiwari</td>
                    <td>Information Technology</td>
                </tr>
                <tr>
                    <td>2</td>
                    <td>Dr. Sanjiv Sharma</td>
                    <td>Information Technology</td>
                </tr>
            </table>
        </body>
        </html>
        """
        p = tmp_path / "table.html"
        p.write_text(html_content, encoding="utf-8")

        doc = parse_html(p)
        all_text = "\n".join(b.text for b in doc.blocks)
        assert "S.No. | Name | Department" in all_text
        assert "1 | Dr. Akhilesh Tiwari | Information Technology" in all_text
        assert "2 | Dr. Sanjiv Sharma | Information Technology" in all_text

    def test_parse_document_dispatch_html(self, tmp_path: Path):
        p = tmp_path / "dispatch.html"
        p.write_text("<html><head><title>Dispatch</title></head><body><p>Hello HTML</p></body></html>", encoding="utf-8")
        doc = parse_document(p, "html")
        assert doc.title == "Dispatch"
        assert "Hello HTML" in doc.blocks[0].text


# ── Test Cross-Document Boilerplate Removal ────────────────────────────

class TestCrossDocumentBoilerplate:
    def test_fewer_than_5_docs_removes_nothing(self):
        # 4 documents with an identical repeating boilerplate line
        docs = []
        for i in range(4):
            docs.append(ParsedDocument(
                blocks=[
                    ParsedBlock(page_number=None, section_title=None, text=f"Document {i} unique body.\nSite Common Navigation Footer"),
                ],
                title=f"Doc {i}",
            ))

        result = remove_cross_document_boilerplate(docs)
        # Corpus < 5 documents: nothing removed
        for d in result:
            assert "Site Common Navigation Footer" in d.blocks[0].text

    def test_boilerplate_removed_at_threshold_and_unique_kept(self):
        # 5 documents: "Global College Footer" in 3 of 5 (60% >= 40%)
        # "Semi Common Notice" in 2 of 5 (40% >= 40%)
        # "Rare Note" in 1 of 5 (20% < 40%)
        docs = [
            ParsedDocument(
                blocks=[ParsedBlock(None, "S1", "Doc 0 unique content.\nGlobal College Footer\nSemi Common Notice\nRare Note")],
                title="Doc 0",
            ),
            ParsedDocument(
                blocks=[ParsedBlock(None, "S1", "Doc 1 unique content.\nGlobal College Footer\nSemi Common Notice")],
                title="Doc 1",
            ),
            ParsedDocument(
                blocks=[ParsedBlock(None, "S1", "Doc 2 unique content.\nGlobal College Footer")],
                title="Doc 2",
            ),
            ParsedDocument(
                blocks=[ParsedBlock(None, "S1", "Doc 3 unique content.")],
                title="Doc 3",
            ),
            ParsedDocument(
                blocks=[ParsedBlock(None, "S1", "Doc 4 unique content.")],
                title="Doc 4",
            ),
        ]

        cleaned = remove_cross_document_boilerplate(docs)
        assert len(cleaned) == 5

        # "Global College Footer" appeared in 3/5 (60%) -> must be removed from all
        for d in cleaned:
            for b in d.blocks:
                assert "Global College Footer" not in b.text

        # "Semi Common Notice" appeared in 2/5 (40%) -> must be removed from all
        for d in cleaned:
            for b in d.blocks:
                assert "Semi Common Notice" not in b.text

        # "Rare Note" appeared in 1/5 (20%) -> must be kept in Doc 0
        assert "Rare Note" in cleaned[0].blocks[0].text
        assert "Doc 0 unique content." in cleaned[0].blocks[0].text


# ── Test PII Redaction ─────────────────────────────────────────────────

class TestRedactPII:
    def test_redact_emails(self):
        text = "Contact us at head_it@mitsgwl.ac.in or support.desk@example.com for queries."
        redacted = redact_pii(text)
        assert redacted == "Contact us at [email] or [email] for queries."

    def test_redact_phone_numbers(self):
        samples = [
            ("Call 9876543210 immediately.", "Call [phone] immediately."),
            ("Helpline: +91 9876543210 or +91-98765-43210.", "Helpline: [phone] or [phone]."),
            ("Format: +91 98765 43210 available.", "Format: [phone] available."),
            ("Direct: 9407204907.", "Direct: [phone]."),
        ]
        for inp, expected in samples:
            assert redact_pii(inp) == expected

    def test_redact_roll_numbers(self):
        text = "Students 0901IT221001 and 0901CS201045 passed the exam."
        redacted = redact_pii(text)
        assert redacted == "Students [roll] and [roll] passed the exam."

    def test_normal_numbers_untouched(self):
        text = "In year 2024, on Page 42, item 1234 cost 12345 in zip 474005 with serial 123456."
        redacted = redact_pii(text)
        assert redacted == text
        assert "2024" in redacted
        assert "Page 42" in redacted
        assert "1234" in redacted
        assert "12345" in redacted
        assert "474005" in redacted
        assert "123456" in redacted

    def test_clean_document_applies_pii_redaction(self):
        doc = ParsedDocument(
            blocks=[
                ParsedBlock(page_number=1, section_title="Contact", text="Email prof@mitsgwl.ac.in or call 9876543210."),
            ],
            title="Contacts",
        )
        cleaned = clean_document(doc)
        assert "[email]" in cleaned.blocks[0].text
        assert "[phone]" in cleaned.blocks[0].text
        assert cleaned.title == "Contacts"
