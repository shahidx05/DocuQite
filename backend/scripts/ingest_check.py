"""
scripts/ingest_check.py — CLI tool to test the parse → clean → chunk pipeline
on a local file WITHOUT touching the database.

Usage (from backend/ with venv active):
    python scripts/ingest_check.py path/to/file.pdf

Prints:
  - page count
  - chunk count
  - min / avg / max chunk character length
  - first 3 chunks with page number and section title
"""

import sys
from pathlib import Path

# Add backend/ to sys.path so "app.*" imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.parsing import parse_document
from app.rag.cleaning import clean_document
from app.rag.chunking import chunk_document


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/ingest_check.py <file_path>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    ext = path.suffix.lstrip(".").lower()
    if ext not in {"pdf", "docx", "pptx"}:
        print(f"Unsupported extension: .{ext}  (supported: pdf, docx, pptx)")
        sys.exit(1)

    print(f"\n── Parsing: {path.name} ──────────────────────────────────────")
    try:
        parsed = parse_document(path, ext)
    except Exception as e:
        print(f"PARSE FAILED: {e}")
        sys.exit(1)

    print(f"Pages / slides: {parsed.page_count}")
    print(f"Blocks (pre-clean): {len(parsed.blocks)}")

    cleaned = clean_document(parsed)
    print(f"Blocks (post-clean): {len(cleaned.blocks)}")

    chunks = chunk_document(cleaned)

    if not chunks:
        print("No chunks produced.")
        sys.exit(0)

    lengths = [c.char_count for c in chunks]
    print(f"\n── Chunk stats ───────────────────────────────────────────────")
    print(f"Chunk count : {len(chunks)}")
    print(f"Min length  : {min(lengths)} chars")
    print(f"Avg length  : {sum(lengths) // len(lengths)} chars")
    print(f"Max length  : {max(lengths)} chars")

    print(f"\n── First 3 chunks ────────────────────────────────────────────")
    for c in chunks[:3]:
        print(f"\n[Chunk {c.chunk_index}]  page={c.page_number}  section={c.section_title!r}")
        print(f"  Length: {c.char_count} chars")
        preview = c.text[:300].replace("\n", "↵")
        print(f"  Text: {preview}{'…' if len(c.text) > 300 else ''}")


if __name__ == "__main__":
    main()
