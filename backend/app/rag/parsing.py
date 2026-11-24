"""
rag/parsing.py — Convert uploaded files into a uniform ParsedDocument structure.

ParsedDocument holds a list of ParsedBlocks, one per page (PDF/PPTX) or logical
section (DOCX). The cleaning and chunking stages receive this structure.

Supported formats:  pdf, docx, pptx, html
"""

from html.parser import HTMLParser
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ParsedBlock:
    """One atomic unit of parsed content."""
    page_number: Optional[int]      # None for DOCX blocks
    section_title: Optional[str]
    text: str


@dataclass
class ParsedDocument:
    blocks: list[ParsedBlock] = field(default_factory=list)
    title: Optional[str] = None

    @property
    def page_count(self) -> int:
        """
        Number of distinct page/slide numbers (None counts as 0 pages for DOCX).
        """
        pages = {b.page_number for b in self.blocks if b.page_number is not None}
        return len(pages) if pages else len(self.blocks)


# ── PDF ────────────────────────────────────────────────────────────────

def _parse_pdf(path: Path) -> ParsedDocument:
    """
    Extract text from a PDF using PyMuPDF.

    Each page is split into sub-blocks at every heading transition so that
    each sub-block carries the section_title that was active at the START of
    its text, not the last heading found on the whole page.

    Heading detection: a line is a heading if its dominant font size is at least
    1.2× the median body-text size on that page and the line is shorter than
    120 chars (avoids flagging long bold paragraphs as headings).

    If the whole PDF yields no text, raises ValueError (scanned PDF).
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    parsed = ParsedDocument()
    # current_section persists across pages so a heading on page N applies
    # to body text on page N+1 that precedes the next heading.
    current_section: Optional[str] = None
    total_text = 0

    for page_num, page in enumerate(doc, start=1):
        blocks_raw = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        # Collect all font sizes to compute the median body-text size.
        all_sizes: list[float] = []
        for blk in blocks_raw:
            if blk["type"] != 0:
                continue
            for line in blk["lines"]:
                for span in line["spans"]:
                    if span["text"].strip():
                        all_sizes.append(span["size"])

        body_size = sorted(all_sizes)[len(all_sizes) // 2] if all_sizes else 12.0
        heading_threshold = body_size * 1.2  # 20% larger → candidate heading

        # Build a flat list of (is_heading, line_text) for this page.
        # We will split into sub-blocks each time we encounter a heading,
        # so the sub-block before a heading does NOT get that heading's title.
        line_records: list[tuple[bool, str]] = []  # (is_heading, text)

        for blk in blocks_raw:
            if blk["type"] != 0:  # skip images
                continue
            for line in blk["lines"]:
                line_text = ""
                is_heading_line = False
                for span in line["spans"]:
                    t = span["text"]
                    line_text += t
                    if span["size"] >= heading_threshold and t.strip():
                        is_heading_line = True
                line_stripped = line_text.strip()
                if not line_stripped:
                    continue
                # Long lines are rarely real section headings even if bold/large.
                if is_heading_line and len(line_stripped) >= 120:
                    is_heading_line = False
                line_records.append((is_heading_line, line_text))

        # Walk the line_records and emit a new sub-block each time a heading
        # is encountered.  The heading line itself starts the new sub-block.
        sub_lines: list[str] = []
        sub_section = current_section  # section active at start of this page

        for is_heading, line_text in line_records:
            if is_heading:
                # Flush accumulated lines as a sub-block (may be empty at page start).
                sub_text = "\n".join(sub_lines).strip()
                if sub_text:
                    total_text += len(sub_text)
                    parsed.blocks.append(ParsedBlock(
                        page_number=page_num,
                        section_title=sub_section,
                        text=sub_text,
                    ))
                # The heading starts a fresh sub-block and updates the active section.
                current_section = line_text.strip()
                sub_section = current_section
                sub_lines = [line_text]  # include heading text in its own sub-block
            else:
                sub_lines.append(line_text)

        # Flush the last sub-block on this page.
        sub_text = "\n".join(sub_lines).strip()
        if sub_text:
            total_text += len(sub_text)
            parsed.blocks.append(ParsedBlock(
                page_number=page_num,
                section_title=sub_section,
                text=sub_text,
            ))

    doc.close()

    if total_text == 0:
        raise ValueError(
            "No extractable text. Scanned PDFs are not supported yet."
        )
    return parsed


# ── DOCX ───────────────────────────────────────────────────────────────

def _table_to_text(table) -> str:
    """Render a docx table as 'col1 | col2 | col3' rows."""
    rows = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _parse_docx(path: Path) -> ParsedDocument:
    """
    Parse a DOCX using python-docx.
    Heading styles become section_title. Tables are included as readable text.
    All blocks are attributed page_number=None (DOCX has no reliable page info).
    """
    from docx import Document as DocxDocument
    from docx.oxml.ns import qn

    doc = DocxDocument(str(path))
    parsed = ParsedDocument()
    current_section: Optional[str] = None
    buffer: list[str] = []

    def _flush():
        text = "\n".join(buffer).strip()
        if text:
            parsed.blocks.append(ParsedBlock(
                page_number=None,
                section_title=current_section,
                text=text,
            ))
        buffer.clear()

    # Iterate body elements in document order (paragraphs + tables).
    body = doc.element.body
    for child in body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            from docx.text.paragraph import Paragraph
            para = Paragraph(child, doc)
            style_name = para.style.name if para.style else ""
            text = para.text.strip()

            if style_name.startswith("Heading"):
                _flush()
                current_section = text or current_section
                if text:
                    buffer.append(text)
            elif text:
                buffer.append(text)

        elif tag == "tbl":
            from docx.table import Table
            tbl = Table(child, doc)
            tbl_text = _table_to_text(tbl)
            if tbl_text.strip():
                buffer.append(tbl_text)

    _flush()
    return parsed


# ── PPTX ───────────────────────────────────────────────────────────────

def _parse_pptx(path: Path) -> ParsedDocument:
    """
    Parse a PPTX using python-pptx. One block per slide.
    slide title → section_title; body + notes are included.
    """
    from pptx import Presentation
    from pptx.util import Pt

    prs = Presentation(str(path))
    parsed = ParsedDocument()

    for slide_num, slide in enumerate(prs.slides, start=1):
        title_text: Optional[str] = None
        body_parts: list[str] = []

        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            # Identify title placeholder
            if hasattr(shape, "placeholder_format") and shape.placeholder_format is not None:
                ph_idx = shape.placeholder_format.idx
                if ph_idx == 0:  # 0 = title placeholder
                    title_text = text
                    continue
            body_parts.append(text)

        # Speaker notes
        if slide.has_notes_slide:
            notes_text = slide.notes_slide.notes_text_frame.text.strip()
            if notes_text:
                body_parts.append(f"Notes: {notes_text}")

        full_text = "\n".join(body_parts).strip()
        if full_text or title_text:
            parsed.blocks.append(ParsedBlock(
                page_number=slide_num,
                section_title=title_text,
                text=full_text,
            ))

    return parsed


# ── HTML ───────────────────────────────────────────────────────────────

_IGNORED_HTML_TAGS = {
    "script", "style", "nav", "header", "footer",
    "aside", "form", "noscript", "svg",
}
_HEADING_TAGS = {"h1", "h2", "h3", "h4"}
_BLOCK_TAGS = {
    "p", "li", "div", "blockquote", "article",
    "section", "main", "hr", "br",
}


class _HTMLDocParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore_depth = 0

        # Title
        self.in_title = False
        self.title_parts: list[str] = []
        self.document_title: Optional[str] = None

        # Heading / sections
        self.current_section: Optional[str] = None
        self.in_heading = False
        self.heading_parts: list[str] = []

        # Tables
        self.in_tr = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row_cells: list[str] = []

        # Regular inline text flow
        self.inline_parts: list[str] = []
        self.block_lines: list[str] = []
        self.blocks: list[ParsedBlock] = []

    def _flush_inline(self):
        """Collapse whitespace in current inline accumulator and push to block_lines."""
        if self.inline_parts:
            text = " ".join("".join(self.inline_parts).split())
            if text:
                self.block_lines.append(text)
            self.inline_parts = []

    def _flush_block(self):
        """Flush accumulated block_lines as a ParsedBlock."""
        self._flush_inline()
        text = "\n".join(self.block_lines).strip()
        if text:
            self.blocks.append(ParsedBlock(
                page_number=None,
                section_title=self.current_section,
                text=text,
            ))
        self.block_lines = []

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower in _IGNORED_HTML_TAGS:
            self.ignore_depth += 1
            return
        if self.ignore_depth > 0:
            return

        if tag_lower == "title":
            self.in_title = True
        elif tag_lower in _HEADING_TAGS:
            self._flush_block()
            self.in_heading = True
            self.heading_parts = []
        elif tag_lower == "tr":
            self._flush_inline()
            self.in_tr = True
            self.row_cells = []
        elif tag_lower in ("td", "th") and self.in_tr:
            self.in_cell = True
            self.cell_parts = []
        elif tag_lower in _BLOCK_TAGS:
            self._flush_inline()

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in _IGNORED_HTML_TAGS:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth > 0:
            return

        if tag_lower == "title":
            self.in_title = False
            title_text = " ".join("".join(self.title_parts).split())
            if title_text:
                self.document_title = title_text
        elif tag_lower in _HEADING_TAGS:
            self.in_heading = False
            heading_text = " ".join("".join(self.heading_parts).split())
            if heading_text:
                self.current_section = heading_text
                self.block_lines.append(heading_text)
            self.heading_parts = []
        elif tag_lower in ("td", "th") and self.in_tr:
            self.in_cell = False
            cell_text = " ".join("".join(self.cell_parts).split())
            self.row_cells.append(cell_text)
            self.cell_parts = []
        elif tag_lower == "tr":
            self.in_tr = False
            if self.row_cells:
                row_str = " | ".join(self.row_cells).strip()
                if row_str:
                    self.block_lines.append(row_str)
            self.row_cells = []
        elif tag_lower in _BLOCK_TAGS:
            self._flush_inline()

    def handle_data(self, data: str):
        if self.ignore_depth > 0:
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        if self.in_heading:
            self.heading_parts.append(data)
            return
        if self.in_cell:
            self.cell_parts.append(data)
            return
        self.inline_parts.append(data)

    def close(self):
        super().close()
        self._flush_block()


def parse_html(path: Path) -> ParsedDocument:
    """
    Parse an HTML document using the standard library html.parser.
    Drops script, style, nav, header, footer, aside, form, noscript and svg content.
    Treats h1-h4 as section titles; page_number stays None.
    Keeps paragraph, list item and table-row text ("a | b | c").
    Uses the <title> as document title.
    """
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="latin-1", errors="ignore")

    parser = _HTMLDocParser()
    parser.feed(content)
    parser.close()

    return ParsedDocument(
        blocks=parser.blocks,
        title=parser.document_title,
    )


# ── Public entry point ─────────────────────────────────────────────────

def parse_document(path: Path, file_type: str) -> ParsedDocument:
    """
    Dispatch to the correct parser based on file_type ("pdf"|"docx"|"pptx"|"html").
    Raises ValueError with a user-friendly message on failure.
    """
    if file_type == "pdf":
        return _parse_pdf(path)
    elif file_type == "docx":
        return _parse_docx(path)
    elif file_type == "pptx":
        return _parse_pptx(path)
    elif file_type == "html":
        return parse_html(path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
