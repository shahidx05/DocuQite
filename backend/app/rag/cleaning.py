"""
rag/cleaning.py — Text normalisation applied to each ParsedBlock before chunking.

Steps (in order):
  1. Fix hyphenated line-break splits  ("manage-\nment" → "management")
  2. Normalise line breaks             (3+ newlines → 2)
  3. Normalise whitespace              (tabs/multiple spaces → single space per line)
  4. Strip leading/trailing whitespace
  5. Drop blocks whose text is empty after cleaning
  6. Remove repeated headers/footers   (short lines on ≥ HEADER_FOOTER_THRESHOLD
     of all pages are assumed to be decorative headers/footers and dropped)

Nothing that could change meaning is removed — only structural/decorative noise.
"""

import re
from typing import Optional

from app.core.config import settings
from app.rag.parsing import ParsedBlock, ParsedDocument

# A line seen on this fraction of pages (or more) is treated as a header/footer.
HEADER_FOOTER_THRESHOLD = 0.6
# Lines shorter than this are candidates for header/footer removal.
HEADER_FOOTER_MAX_LEN = 80

# Thresholds for cross-document HTML boilerplate removal
CROSS_DOCUMENT_BOILERPLATE_THRESHOLD = 0.40
MIN_CORPUS_SIZE_FOR_BOILERPLATE = 5

# ── PII Patterns ───────────────────────────────────────────────────────
# Email addresses
PII_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
# Roll / enrolment numbers e.g. 0901IT221001, 0901CS201045
PII_ROLL_PATTERN = re.compile(
    r"\b0901[A-Za-z0-9]{6,12}\b",
    re.IGNORECASE,
)
# 10-digit phone numbers with optional +91, single spaces or dashes between digits.
# Uses lookarounds to leave 4-digit years, page numbers, and 4-6 digit numbers untouched.
PII_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?91[\s\-]?)?(?:(?:\d[\s\-]?){9}\d)(?!\d)"
)


def redact_pii(text: str) -> str:
    """
    Redact Personally Identifiable Information (PII) from text:
      - Email addresses -> [email]
      - Enrolment patterns like 0901IT221001 -> [roll]
      - 10-digit phone numbers (with optional +91 or spaces/dashes) -> [phone]

    Leaves normal numbers (years, page numbers, 4-6 digit numbers) untouched.
    Never logs matched values.
    """
    if not text:
        return text

    # Redaction order: email first, then enrolment roll numbers, then phone numbers
    text = PII_EMAIL_PATTERN.sub("[email]", text)
    text = PII_ROLL_PATTERN.sub("[roll]", text)
    text = PII_PHONE_PATTERN.sub("[phone]", text)
    return text


def remove_cross_document_boilerplate(
    docs: list[ParsedDocument],
    threshold: float = CROSS_DOCUMENT_BOILERPLATE_THRESHOLD,
    min_docs: int = MIN_CORPUS_SIZE_FOR_BOILERPLATE,
) -> list[ParsedDocument]:
    """
    Remove lines that appear in at least `threshold` (default 40%) of the documents.
    If the corpus has fewer than `min_docs` (default 5) documents, no lines are removed.
    Preserves document title, block page numbers, and section titles.
    """
    if len(docs) < min_docs:
        return docs

    num_docs = len(docs)
    # Count how many distinct documents contain each stripped line
    line_doc_freq: dict[str, int] = {}
    for doc in docs:
        seen_in_doc: set[str] = set()
        for block in doc.blocks:
            for raw_line in block.text.split("\n"):
                line = raw_line.strip()
                if line:
                    seen_in_doc.add(line)
        for line in seen_in_doc:
            line_doc_freq[line] = line_doc_freq.get(line, 0) + 1

    # Lines appearing in >= threshold fraction of documents are boilerplate
    boilerplate_lines = {
        line for line, count in line_doc_freq.items()
        if (count / num_docs) >= threshold
    }

    if not boilerplate_lines:
        return docs

    result_docs: list[ParsedDocument] = []
    for doc in docs:
        cleaned_blocks: list[ParsedBlock] = []
        for block in doc.blocks:
            kept_lines = [
                line for line in block.text.split("\n")
                if line.strip() not in boilerplate_lines
            ]
            new_text = "\n".join(kept_lines).strip()
            new_text = re.sub(r"\n{3,}", "\n\n", new_text)
            if new_text:
                cleaned_blocks.append(ParsedBlock(
                    page_number=block.page_number,
                    section_title=block.section_title,
                    text=new_text,
                ))
        result_docs.append(ParsedDocument(
            blocks=cleaned_blocks,
            title=doc.title,
        ))

    return result_docs


def _clean_text(text: str) -> str:
    """Apply normalisation rules to a single text string."""
    # Replace non-breaking spaces
    text = text.replace("\xa0", " ")

    # 1. Fix soft-hyphen line breaks: "manage-\nment" → "management"
    text = re.sub(r"-\n(\S)", lambda m: m.group(1), text)

    # 2. Collapse 3+ consecutive newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 3. Normalise whitespace within each line (tabs / multiple spaces → one space)
    lines = [re.sub(r"[ \t]+", " ", line) for line in text.split("\n")]
    text = "\n".join(lines)

    # 4. Strip
    return text.strip()


def _find_repeated_lines(blocks: list[ParsedBlock], page_count: int) -> set[str]:
    """
    Return the set of short lines that appear on ≥ HEADER_FOOTER_THRESHOLD of pages.
    Only examines blocks that have a page_number (PDF/PPTX).
    """
    if page_count == 0:
        return set()

    # Map: line_text → set of page numbers it appears on
    line_pages: dict[str, set[int]] = {}
    for block in blocks:
        if block.page_number is None:
            continue
        for raw_line in block.text.split("\n"):
            line = raw_line.strip()
            if line and len(line) <= HEADER_FOOTER_MAX_LEN:
                line_pages.setdefault(line, set()).add(block.page_number)

    threshold_count = max(2, int(page_count * HEADER_FOOTER_THRESHOLD))
    return {line for line, pages in line_pages.items() if len(pages) >= threshold_count}


def clean_document(parsed: ParsedDocument) -> ParsedDocument:
    """
    Clean all blocks in-place (returns a new ParsedDocument with cleaned blocks).
    """
    page_count = parsed.page_count
    repeated = _find_repeated_lines(parsed.blocks, page_count)

    cleaned_blocks: list[ParsedBlock] = []
    for block in parsed.blocks:
        text = _clean_text(block.text)

        # Remove repeated header/footer lines from this block's text
        if repeated:
            kept_lines = [
                line for line in text.split("\n")
                if line.strip() not in repeated
            ]
            text = "\n".join(kept_lines).strip()
            # Re-collapse after removal
            text = re.sub(r"\n{3,}", "\n\n", text)

        # Redact PII if configured
        if getattr(settings, "REDACT_PII", True):
            text = redact_pii(text)

        if text:
            cleaned_blocks.append(ParsedBlock(
                page_number=block.page_number,
                section_title=block.section_title,
                text=text,
            ))

    result = ParsedDocument(title=parsed.title)
    result.blocks = cleaned_blocks
    return result
