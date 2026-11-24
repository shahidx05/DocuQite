"""
scripts/college_audit.py — Read-only audit of college dataset (PDFs and HTML pages).

Scans:
  1. data/raw/college/pdfs
  2. data/raw/college/pages

Outputs a comprehensive audit covering:
  - PDF file sizes, parsing, classification (TEXT, LOW_TEXT, SCANNED), chunk estimates.
  - HTML visible text extraction (via stdlib html.parser), title extraction, text volume.
  - Privacy scan: lines matching emails, 10-digit phone numbers, and roll number patterns.
    (Counts only, values are NEVER printed or persisted).

Writes report to data/college_audit.txt and stdout.
"""

import os
import re
import sys
from html.parser import HTMLParser
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

import fitz  # PyMuPDF
from app.core.config import settings
from app.rag.chunking import chunk_document
from app.rag.cleaning import clean_document
from app.rag.parsing import parse_document

# ── Helpers ─────────────────────────────────────────────────────────────

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


class HTMLVisibleTextParser(HTMLParser):
    """Extract visible text from HTML using stdlib html.parser, stripping script, style, and nav."""

    def __init__(self):
        super().__init__()
        self.in_ignored_tag = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.ignored_tags = {"script", "style", "nav"}

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        if tag_lower in self.ignored_tags:
            self.in_ignored_tag += 1
        elif tag_lower == "title":
            self.in_title = True

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if tag_lower in self.ignored_tags:
            self.in_ignored_tag = max(0, self.in_ignored_tag - 1)
        elif tag_lower == "title":
            self.in_title = False

    def handle_data(self, data: str):
        if self.in_title:
            self.title_parts.append(data)
        if self.in_ignored_tag == 0:
            self.text_parts.append(data)

    def get_title(self) -> str:
        raw_title = " ".join("".join(self.title_parts).split())
        return raw_title.strip()

    def get_visible_text(self) -> str:
        raw_text = "".join(self.text_parts)
        lines = [line.strip() for line in raw_text.splitlines()]
        return "\n".join(l for l in lines if l)


# Privacy patterns
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+?91[\-\s]?)?[6-9]\d{9})(?!\d)")
ROLL_RE = re.compile(r"\b0901(?:[A-Za-z]{2,4}\d+|\d{6,10}|[A-Za-z0-9]{6,12})\b", re.IGNORECASE)


def scan_privacy_lines(text: str) -> tuple[int, int, int]:
    """
    Returns (email_lines, phone_lines, roll_lines).
    Never returns or exposes the matched strings.
    """
    email_lines = 0
    phone_lines = 0
    roll_lines = 0

    for line in text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        if EMAIL_RE.search(line_str):
            email_lines += 1
        if PHONE_RE.search(line_str):
            phone_lines += 1
        if ROLL_RE.search(line_str):
            roll_lines += 1

    return email_lines, phone_lines, roll_lines


def main():
    pdfs_dir = ROOT_DIR / "data" / "raw" / "college" / "pdfs"
    pages_dir = ROOT_DIR / "data" / "raw" / "college" / "pages"
    output_file = ROOT_DIR / "data" / "college_audit.txt"

    lines_out: list[str] = []

    def log(msg: str = ""):
        print(msg)
        lines_out.append(msg)

    log("=" * 80)
    log("COLLEGE DATASET READ-ONLY AUDIT REPORT")
    log("=" * 80)
    log(f"Root Directory: {ROOT_DIR}")
    log(f"PDFs Directory: {pdfs_dir}")
    log(f"Pages Directory: {pages_dir}")
    log(f"MAX_UPLOAD_MB Threshold: {settings.MAX_UPLOAD_MB} MB ({settings.MAX_UPLOAD_MB * 1024 * 1024:,} bytes)")
    log()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. PDF AUDIT
    # ─────────────────────────────────────────────────────────────────────────
    log("-" * 80)
    log("1. PDF DOCUMENTS AUDIT")
    log("-" * 80)

    pdf_files = sorted(list(pdfs_dir.glob("*.pdf")), key=lambda p: p.name.lower())
    total_pdf_count = len(pdf_files)
    total_pdf_bytes = sum(p.stat().st_size for p in pdf_files)
    max_upload_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    exceed_upload_limit = [p for p in pdf_files if p.stat().st_size > max_upload_bytes]

    log(f"Total PDF count:        {total_pdf_count}")
    log(f"Total PDF size:         {format_size(total_pdf_bytes)} ({total_pdf_bytes:,} bytes)")
    log(f"Exceeding MAX_UPLOAD_MB: {len(exceed_upload_limit)}")
    if exceed_upload_limit:
        for p in exceed_upload_limit:
            log(f"  - {p.name}: {format_size(p.stat().st_size)}")
    log()

    # Process each PDF
    pdf_records = []
    # Structure: dict(name, size, pages, chars, avg_chars, classification, chunks, text)
    privacy_records = []

    text_pdf_total_pages = 0
    text_pdf_total_chunks = 0
    class_counts = {"TEXT": 0, "LOW_TEXT": 0, "SCANNED": 0}

    for idx, p in enumerate(pdf_files, start=1):
        file_size = p.stat().st_size
        doc = fitz.open(str(p))
        page_count = len(doc)
        doc.close()

        extracted_text = ""
        try:
            parsed = parse_document(p, "pdf")
            cleaned = clean_document(parsed)
            extracted_text = "\n".join(b.text for b in cleaned.blocks)
            char_count = sum(len(b.text) for b in cleaned.blocks)
        except Exception:
            char_count = 0
            extracted_text = ""

        avg_chars = char_count / page_count if page_count > 0 else 0.0

        if avg_chars >= 200.0:
            classification = "TEXT"
            class_counts["TEXT"] += 1
            text_pdf_total_pages += page_count
            # Estimate chunk count using existing chunker
            try:
                chunks = chunk_document(cleaned)
                chunk_count = len(chunks)
            except Exception:
                chunk_count = 0
            text_pdf_total_chunks += chunk_count
        elif avg_chars < 10.0 or char_count < 50:
            classification = "SCANNED"
            class_counts["SCANNED"] += 1
            chunk_count = 0
        else:
            classification = "LOW_TEXT"
            class_counts["LOW_TEXT"] += 1
            chunk_count = 0

        # Privacy scan for this PDF
        em_cnt, ph_cnt, rl_cnt = scan_privacy_lines(extracted_text)
        tot_pii = em_cnt + ph_cnt + rl_cnt
        if tot_pii > 0:
            privacy_records.append({
                "file": p.name,
                "type": "PDF",
                "emails": em_cnt,
                "phones": ph_cnt,
                "rolls": rl_cnt,
                "total": tot_pii,
            })

        pdf_records.append({
            "name": p.name,
            "path": p,
            "size": file_size,
            "pages": page_count,
            "chars": char_count,
            "avg_chars": avg_chars,
            "class": classification,
            "chunks": chunk_count,
        })

    log("PDF CLASSIFICATION SUMMARY:")
    log(f"  - TEXT PDFs (avg >= 200 chars/page):   {class_counts['TEXT']:3d} ({class_counts['TEXT'] / total_pdf_count * 100:.1f}%)")
    log(f"  - LOW_TEXT PDFs (10 <= avg < 200):     {class_counts['LOW_TEXT']:3d} ({class_counts['LOW_TEXT'] / total_pdf_count * 100:.1f}%)")
    log(f"  - SCANNED PDFs (near zero text):       {class_counts['SCANNED']:3d} ({class_counts['SCANNED'] / total_pdf_count * 100:.1f}%)")
    log(f"  - Total pages in TEXT PDFs:            {text_pdf_total_pages:,}")
    log(f"  - Total chunks produced for TEXT PDFs: {text_pdf_total_chunks:,}")
    log()

    # List the 15 largest files
    largest_15 = sorted(pdf_records, key=lambda r: r["size"], reverse=True)[:15]
    log("TOP 15 LARGEST PDF FILES:")
    log(f"{'#':<3} {'Size':<10} {'Pages':<7} {'Class':<10} {'Filename'}")
    log("-" * 80)
    for i, r in enumerate(largest_15, 1):
        log(f"{i:<3} {format_size(r['size']):<10} {r['pages']:<7} {r['class']:<10} {r['name']}")
    log()

    # List 15 SCANNED / LOW_TEXT files
    scanned_low = [r for r in pdf_records if r["class"] in ("SCANNED", "LOW_TEXT")]
    scanned_15 = scanned_low[:15]
    log(f"15 SCANNED / LOW_TEXT FILES (Sample of {len(scanned_low)} total):")
    log(f"{'#':<3} {'Class':<10} {'Pages':<7} {'Chars':<9} {'Avg/Page':<9} {'Filename'}")
    log("-" * 80)
    for i, r in enumerate(scanned_15, 1):
        log(f"{i:<3} {r['class']:<10} {r['pages']:<7} {r['chars']:<9} {r['avg_chars']:<9.1f} {r['name']}")
    log()

    # ─────────────────────────────────────────────────────────────────────────
    # 2. HTML PAGES AUDIT
    # ─────────────────────────────────────────────────────────────────────────
    log("-" * 80)
    log("2. HTML WEBPAGES AUDIT")
    log("-" * 80)

    html_files = sorted(list(pages_dir.glob("*.html")), key=lambda p: p.name.lower())
    total_html_count = len(html_files)
    total_html_bytes = sum(p.stat().st_size for p in html_files)

    html_records = []
    total_visible_chars = 0
    pages_under_500_chars = 0

    log(f"{'#':<3} {'File Size':<10} {'Visible Chars':<15} {'Title / Filename'}")
    log("-" * 80)

    for i, p in enumerate(html_files, 1):
        file_size = p.stat().st_size
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            content = ""

        parser = HTMLVisibleTextParser()
        parser.feed(content)
        title = parser.get_title() or "(no title)"
        visible_text = parser.get_visible_text()
        vis_len = len(visible_text)

        total_visible_chars += vis_len
        if vis_len < 500:
            pages_under_500_chars += 1

        # Privacy scan for HTML
        em_cnt, ph_cnt, rl_cnt = scan_privacy_lines(visible_text)
        tot_pii = em_cnt + ph_cnt + rl_cnt
        if tot_pii > 0:
            privacy_records.append({
                "file": p.name,
                "type": "HTML",
                "emails": em_cnt,
                "phones": ph_cnt,
                "rolls": rl_cnt,
                "total": tot_pii,
            })

        html_records.append({
            "name": p.name,
            "size": file_size,
            "vis_len": vis_len,
            "title": title,
        })

        log(f"{i:<3} {format_size(file_size):<10} {vis_len:<15,d} {title[:60]}")
        log(f"    ↳ File: {p.name}")

    log()
    log("HTML SUMMARY:")
    log(f"  - Total HTML pages:           {total_html_count}")
    log(f"  - Total raw size:             {format_size(total_html_bytes)} ({total_html_bytes:,} bytes)")
    log(f"  - Total visible text chars:   {total_visible_chars:,}")
    log(f"  - Average visible chars/page: {total_visible_chars / total_html_count:.1f}")
    log(f"  - Pages under 500 characters: {pages_under_500_chars} ({pages_under_500_chars / total_html_count * 100:.1f}%)")
    log()

    # ─────────────────────────────────────────────────────────────────────────
    # 3. PRIVACY SCAN
    # ─────────────────────────────────────────────────────────────────────────
    log("-" * 80)
    log("3. PRIVACY SCAN (PII MATCH COUNTS ONLY — NO VALUES DISCLOSED)")
    log("-" * 80)

    # Sort privacy records by total detected lines descending
    top_privacy = sorted(privacy_records, key=lambda r: r["total"], reverse=True)[:15]

    log(f"{'#':<3} {'Type':<6} {'Total Lines':<13} {'Email Lines':<13} {'Phone Lines':<13} {'Roll Lines':<13} {'Filename'}")
    log("-" * 95)
    for i, r in enumerate(top_privacy, 1):
        log(f"{i:<3} {r['type']:<6} {r['total']:<13d} {r['emails']:<13d} {r['phones']:<13d} {r['rolls']:<13d} {r['file']}")
    log()

    # Summary of privacy findings
    total_email_lines = sum(r["emails"] for r in privacy_records)
    total_phone_lines = sum(r["phones"] for r in privacy_records)
    total_roll_lines = sum(r["rolls"] for r in privacy_records)
    total_pii_files = len(privacy_records)

    log("PRIVACY SCAN TOTALS:")
    log(f"  - Files containing potential PII: {total_pii_files} (out of {total_pdf_count + total_html_count} total files)")
    log(f"  - Total email address lines:      {total_email_lines:,}")
    log(f"  - Total phone number lines:       {total_phone_lines:,}")
    log(f"  - Total roll/enrolment lines:     {total_roll_lines:,}")
    log()
    log("=" * 80)
    log("AUDIT COMPLETED")
    log("=" * 80)

    # Write report to data/college_audit.txt
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")

    print(f"\n[Audit report successfully written to: {output_file}]")


if __name__ == "__main__":
    main()
