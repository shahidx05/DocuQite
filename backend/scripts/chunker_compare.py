"""
scripts/chunker_compare.py — Compare custom vs. LangChain chunkers on a document.

Usage:
    python scripts/chunker_compare.py <file_path>

Runs both chunkers without touching the database and prints for each:
- Chunk count
- Min / Avg / Max length (in characters)
- Number of chunks that start mid-word
- Number of chunks with a section_title
"""

import sys
from pathlib import Path

# Add backend directory to path if running directly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.rag.chunking import CustomChunker, LangChainChunker, TextChunk, _group_blocks
from app.rag.cleaning import clean_document
from app.rag.parsing import parse_document


def count_mid_word_chunks(chunks: list[TextChunk], groups: list[tuple]) -> int:
    """
    Count chunks whose starting characters cut into the middle of an alphanumeric word
    in the source text.
    """
    mid_word_count = 0
    for page_num, section_title, group_text in groups:
        group_chunks = [
            c for c in chunks
            if c.section_title == section_title and (page_num is None or c.page_number == page_num)
        ]
        last_idx = 0
        for c in group_chunks:
            probe = c.text[: min(30, len(c.text))].strip()
            if not probe:
                continue
            pos = group_text.find(probe, last_idx)
            if pos == -1:
                pos = group_text.find(probe)
            if pos > 0 and group_text[pos - 1].isalnum() and probe[0].isalnum():
                mid_word_count += 1
            if pos != -1:
                last_idx = pos + 1
    return mid_word_count


def analyze_chunks(name: str, chunks: list[TextChunk], groups: list[tuple]) -> dict:
    count = len(chunks)
    lengths = [c.char_count for c in chunks]
    min_len = min(lengths) if lengths else 0
    max_len = max(lengths) if lengths else 0
    avg_len = round(sum(lengths) / count, 1) if count else 0.0
    mid_word = count_mid_word_chunks(chunks, groups)
    with_section = sum(1 for c in chunks if c.section_title is not None and c.section_title.strip() != "")

    return {
        "chunker": name,
        "count": count,
        "min_len": min_len,
        "avg_len": avg_len,
        "max_len": max_len,
        "mid_word": mid_word,
        "with_section": with_section,
    }


def compare_file(file_path_str: str) -> None:
    path = Path(file_path_str).resolve()
    if not path.exists():
        print(f"Error: file not found at {path}")
        sys.exit(1)

    ext = path.suffix.lower().lstrip(".")
    if ext not in ("pdf", "docx", "pptx"):
        print(f"Error: unsupported file extension '{ext}'. Must be pdf, docx, or pptx.")
        sys.exit(1)

    print(f"\n========================================================")
    print(f" Chunker Comparison on: {path.name}")
    print(f"========================================================")

    parsed = parse_document(path, ext)
    cleaned = clean_document(parsed)
    groups = _group_blocks(cleaned)

    custom_chunker = CustomChunker()
    custom_chunks = custom_chunker.chunk(cleaned)
    custom_stats = analyze_chunks("Custom", custom_chunks, groups)

    langchain_chunker = LangChainChunker()
    langchain_chunks = langchain_chunker.chunk(cleaned)
    langchain_stats = analyze_chunks("LangChain", langchain_chunks, groups)

    header = f"{'Metric':<32} | {'Custom Chunker':<16} | {'LangChain Chunker':<16}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    print(f"{'Chunk count':<32} | {custom_stats['count']:<16} | {langchain_stats['count']:<16}")
    print(f"{'Min chunk length (chars)':<32} | {custom_stats['min_len']:<16} | {langchain_stats['min_len']:<16}")
    print(f"{'Avg chunk length (chars)':<32} | {custom_stats['avg_len']:<16} | {langchain_stats['avg_len']:<16}")
    print(f"{'Max chunk length (chars)':<32} | {custom_stats['max_len']:<16} | {langchain_stats['max_len']:<16}")
    print(f"{'Chunks starting mid-word':<32} | {custom_stats['mid_word']:<16} | {langchain_stats['mid_word']:<16}")
    print(f"{'Chunks with section_title':<32} | {custom_stats['with_section']:<16} | {langchain_stats['with_section']:<16}")
    print(sep)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/chunker_compare.py <path-to-document>")
        sys.exit(1)
    compare_file(sys.argv[1])
