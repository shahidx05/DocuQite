"""
rag/chunking.py — Structure-aware recursive text chunker.

Algorithm:
  1. Never merge text across different section_titles.
  2. Split order: paragraph breaks → sentences → words → characters.
  3. Respect CHUNK_SIZE and CHUNK_OVERLAP from settings.
  4. Adjacent small blocks from the SAME section are merged before splitting.
  5. Deterministic: same input always produces the same chunks.

Each output Chunk carries the page_number and section_title of the source block.
"""

import re
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.rag.parsing import ParsedBlock, ParsedDocument


@dataclass
class TextChunk:
    chunk_index: int
    page_number: Optional[int]
    section_title: Optional[str]
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


# ── Splitting primitives ───────────────────────────────────────────────

def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_sentences(text: str) -> list[str]:
    # Simple sentence splitter: split on ". " / "? " / "! " followed by uppercase
    parts = re.split(r"(?<=[.?!])\s+(?=[A-Z\"\'(])", text)
    return [p.strip() for p in parts if p.strip()]


def _split_words(text: str) -> list[str]:
    return text.split()


def _split_to_fit(text: str, max_size: int) -> list[str]:
    """
    Recursively split *text* into pieces ≤ max_size chars.
    Split order: paragraphs → sentences → words → characters.
    """
    if len(text) <= max_size:
        return [text]

    # Try paragraph split
    paras = _split_paragraphs(text)
    if len(paras) > 1:
        return _merge_and_split(paras, max_size)

    # Try sentence split
    sents = _split_sentences(text)
    if len(sents) > 1:
        return _merge_and_split(sents, max_size)

    # Try word split
    words = _split_words(text)
    if len(words) > 1:
        return _merge_and_split(words, max_size, joiner=" ")

    # Last resort: character split (e.g. very long URL or CJK text)
    return [text[i : i + max_size] for i in range(0, len(text), max_size)]


def _merge_and_split(pieces: list[str], max_size: int, joiner: str = "\n\n") -> list[str]:
    """
    Greedily join pieces into chunks ≤ max_size, then recursively split
    any piece that is still too large.
    """
    result: list[str] = []
    current = ""
    for piece in pieces:
        if len(piece) > max_size:
            if current:
                result.append(current)
                current = ""
            result.extend(_split_to_fit(piece, max_size))
        elif current and len(current) + len(joiner) + len(piece) > max_size:
            result.append(current)
            current = piece
        else:
            current = (current + joiner + piece).strip() if current else piece
    if current:
        result.append(current)
    return result


# ── Overlap helper ─────────────────────────────────────────────────────

def _add_overlap(chunks: list[str], overlap: int) -> list[str]:
    """
    Prepend the tail of the previous chunk to the current chunk so that
    context is not lost at chunk boundaries.

    The overlap slice always starts at a word boundary.  After taking
    chunks[i-1][-overlap:] we advance the start forward to the first
    whitespace character and use the text after it, so we never carry
    a partial word.  If the slice contains no whitespace at all (the
    entire slice is inside one long word), we skip the overlap for that
    boundary rather than emit a mid-word fragment.
    """
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    result = [chunks[0]]
    for i in range(1, len(chunks)):
        raw_tail = chunks[i - 1][-overlap:]
        # Find first whitespace to snap to a word boundary.
        ws_match = re.search(r"\s", raw_tail)
        if ws_match:
            # Take everything after the first whitespace (i.e. start of a full word).
            prev_tail = raw_tail[ws_match.end():].strip()
        else:
            # Entire slice is inside one word — omit overlap rather than cut mid-word.
            prev_tail = ""
        if prev_tail:
            result.append((prev_tail + "\n" + chunks[i]).strip())
        else:
            result.append(chunks[i].strip())
    return result


# ── Block grouping helper ──────────────────────────────────────────────

def _group_blocks(parsed: ParsedDocument) -> list[tuple[Optional[int], Optional[str], str]]:
    """
    Group adjacent blocks that share the same section_title.
    A section change forces a flush so we never merge across sections.
    """
    groups: list[tuple[Optional[int], Optional[str], str]] = []
    current_title: Optional[str] = None
    current_page: Optional[int] = None
    buffer: list[str] = []

    def _flush_group():
        if buffer:
            groups.append((current_page, current_title, "\n\n".join(buffer)))
            buffer.clear()

    for block in parsed.blocks:
        if block.section_title != current_title:
            _flush_group()
            current_title = block.section_title
            current_page = block.page_number
        elif current_page is None and block.page_number is not None:
            current_page = block.page_number
        buffer.append(block.text)

    _flush_group()
    return groups


# ── Chunker Classes ────────────────────────────────────────────────────

class CustomChunker:
    """Structure-aware recursive text chunker with word-boundary snapping."""

    def __init__(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    def chunk(self, parsed: ParsedDocument) -> list[TextChunk]:
        groups = _group_blocks(parsed)
        all_chunks: list[TextChunk] = []
        idx = 0
        for page_num, section_title, text in groups:
            raw_pieces = _split_to_fit(text, self.chunk_size)
            with_overlap = _add_overlap(raw_pieces, self.chunk_overlap)
            for piece in with_overlap:
                if piece.strip():
                    all_chunks.append(TextChunk(
                        chunk_index=idx,
                        page_number=page_num,
                        section_title=section_title,
                        text=piece.strip(),
                    ))
                    idx += 1
        return all_chunks


class LangChainChunker:
    """LangChain RecursiveCharacterTextSplitter wrapper matching TextChunk structure."""

    def __init__(self, chunk_size: Optional[int] = None, chunk_overlap: Optional[int] = None):
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def chunk(self, parsed: ParsedDocument) -> list[TextChunk]:
        groups = _group_blocks(parsed)
        all_chunks: list[TextChunk] = []
        idx = 0
        for page_num, section_title, text in groups:
            pieces = self.splitter.split_text(text)
            for piece in pieces:
                if piece.strip():
                    all_chunks.append(TextChunk(
                        chunk_index=idx,
                        page_number=page_num,
                        section_title=section_title,
                        text=piece.strip(),
                    ))
                    idx += 1
        return all_chunks


# ── Public entry point & factory ────────────────────────────────────────

def get_chunker(name: Optional[str] = None):
    """
    Chunker factory function.
    Reads CHUNKER from settings if name is not explicitly passed.
    Raises ValueError on unknown chunker name.
    """
    chunker_name = (name or settings.CHUNKER).lower().strip()
    if chunker_name == "custom":
        return CustomChunker()
    elif chunker_name == "langchain":
        return LangChainChunker()
    else:
        raise ValueError(
            f"Unknown CHUNKER: {chunker_name!r}. Supported values are 'custom' and 'langchain'."
        )


def chunk_document(parsed: ParsedDocument) -> list[TextChunk]:
    """
    Public entry point for chunking.
    Uses chunker selected by settings.CHUNKER (default: 'custom').
    """
    return get_chunker().chunk(parsed)
