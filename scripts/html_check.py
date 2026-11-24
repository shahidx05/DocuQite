"""
scripts/html_check.py — Phase 3B-1 verification script for HTML parsing,
cross-page boilerplate removal, PII redaction, and chunking.

Usage:
    python scripts/html_check.py [folder]
Default folder: data/raw/college/pages
"""

import sys
from pathlib import Path

# Resolve project root and backend path
SCRIPT_PATH = Path(__file__).resolve()
if SCRIPT_PATH.parent.name == "scripts":
    ROOT_DIR = SCRIPT_PATH.parent.parent
elif SCRIPT_PATH.parent.name == "backend":
    ROOT_DIR = SCRIPT_PATH.parent.parent
else:
    ROOT_DIR = SCRIPT_PATH.parent

BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.rag.chunking import chunk_document
from app.rag.cleaning import (
    clean_document,
    redact_pii,
    remove_cross_document_boilerplate,
)
from app.rag.parsing import ParsedBlock, ParsedDocument, parse_html


def main():
    folder_arg = sys.argv[1] if len(sys.argv) > 1 else str(ROOT_DIR / "data/raw/college/pages")
    folder = Path(folder_arg)
    if not folder.is_absolute():
        folder = ROOT_DIR / folder

    if not folder.exists() or not folder.is_dir():
        print(f"Error: Folder not found: {folder}")
        sys.exit(1)

    html_files = sorted(list(folder.glob("*.html")) + list(folder.glob("*.htm")))
    if not html_files:
        print(f"Error: No HTML files found in: {folder}")
        sys.exit(1)

    print("=" * 80)
    print("HTML PROCESSING CHECK (Phase 3B-1)")
    print(f"Target folder: {folder}")
    print(f"Total HTML files found: {len(html_files)}")
    print("=" * 80)

    # 1. Parse all HTML files
    raw_docs: list[tuple[Path, ParsedDocument, int]] = []
    for file_path in html_files:
        doc = parse_html(file_path)
        chars_before = sum(len(b.text) for b in doc.blocks)
        raw_docs.append((file_path, doc, chars_before))

    # 2. Cross-document boilerplate removal
    all_parsed_docs = [item[1] for item in raw_docs]
    docs_after_bp = remove_cross_document_boilerplate(all_parsed_docs)

    # 3. PII redaction & chunking per document
    processed_results = []
    total_chars_before = 0
    total_chars_after = 0
    total_chunks = 0

    for (file_path, _, chars_before), doc_clean in zip(raw_docs, docs_after_bp):
        # Redact PII on each block
        redacted_blocks = []
        for block in doc_clean.blocks:
            redacted_text = redact_pii(block.text)
            if redacted_text.strip():
                redacted_blocks.append(ParsedBlock(
                    page_number=block.page_number,
                    section_title=block.section_title,
                    text=redacted_text,
                ))

        processed_doc = ParsedDocument(
            blocks=redacted_blocks,
            title=doc_clean.title,
        )

        chars_after = sum(len(b.text) for b in processed_doc.blocks)
        chunks = chunk_document(processed_doc)

        total_chars_before += chars_before
        total_chars_after += chars_after
        total_chunks += len(chunks)

        processed_results.append({
            "path": file_path,
            "filename": file_path.name,
            "title": processed_doc.title or "(No Title)",
            "chars_before": chars_before,
            "chars_after": chars_after,
            "chars_dropped": chars_before - chars_after,
            "chunk_count": len(chunks),
            "chunks": chunks,
        })

    # Print summary table
    print(f"\n{'#':<3} {'Before':<10} {'After':<10} {'Dropped':<10} {'Chunks':<8} {'Title / Filename'}")
    print("-" * 80)
    for i, r in enumerate(processed_results, start=1):
        print(f"{i:<3} {r['chars_before']:<10} {r['chars_after']:<10} {r['chars_dropped']:<10} {r['chunk_count']:<8} {r['title']}")
        print(f"    ↳ File: {r['filename']}")

    dropped_total = total_chars_before - total_chars_after
    dropped_pct = (dropped_total / total_chars_before * 100) if total_chars_before > 0 else 0.0

    print("\n" + "=" * 80)
    print("TOTALS SUMMARY:")
    print(f"  - Total HTML files:             {len(html_files)}")
    print(f"  - Total visible chars (before): {total_chars_before:,}")
    print(f"  - Total visible chars (after):  {total_chars_after:,}")
    print(f"  - Total boilerplate dropped:    {dropped_total:,} chars ({dropped_pct:.1f}%)")
    print(f"  - Total chunks produced:        {total_chunks:,}")
    print("=" * 80)

    # Print first 3 chunks of 2 different pages
    candidates = [r for r in processed_results if r["chunk_count"] >= 3]
    if len(candidates) < 2:
        candidates = processed_results[:2]

    sample_pages = candidates[:2]
    print("\n" + "=" * 80)
    print("SAMPLE CHUNKS (First 3 chunks of 2 different pages):")
    print("=" * 80)

    for page_idx, page in enumerate(sample_pages, start=1):
        print(f"\n--- SAMPLE PAGE {page_idx}: {page['title']} ---")
        print(f"Filename: {page['filename']}")
        print(f"Total Chunks: {page['chunk_count']}")

        for chunk in page["chunks"][:3]:
            print(f"\n  [Chunk {chunk.chunk_index}] Section: {chunk.section_title!r} | Chars: {len(chunk.text)}")
            print("  " + "-" * 60)
            for line in chunk.text.split("\n")[:8]:
                print(f"  | {line}")
            if len(chunk.text.split("\n")) > 8:
                print("  | ... (truncated for display)")

    print("\n" + "=" * 80)
    print("HTML CHECK COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()
