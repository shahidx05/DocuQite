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

from app.rag.parsing import ParsedBlock, ParsedDocument

# A line seen on this fraction of pages (or more) is treated as a header/footer.
HEADER_FOOTER_THRESHOLD = 0.6
# Lines shorter than this are candidates for header/footer removal.
HEADER_FOOTER_MAX_LEN = 80


def _clean_text(text: str) -> str:
    """Apply normalisation rules to a single text string."""
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

        if text:
            cleaned_blocks.append(ParsedBlock(
                page_number=block.page_number,
                section_title=block.section_title,
                text=text,
            ))

    result = ParsedDocument()
    result.blocks = cleaned_blocks
    return result
