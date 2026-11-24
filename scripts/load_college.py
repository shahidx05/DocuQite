"""
scripts/load_college.py — College corpus loader (Phase 3B-2).

Loads the audited college dataset into the "College" workspace:
  - 29 HTML pages (with cross-page boilerplate removal across the corpus)
  - Up to 60 filtered TEXT-class PDFs (<= 25 MB, zero roll numbers, < 5 emails/phones,
    excluding administrative lists/marks, prioritized by category variety:
    syllabus, schemes, circulars/notices, BoS, reports, then other capped at 10)

Usage:
  python scripts/load_college.py [--dry-run]
  python scripts/load_college.py --apply --user-email <email>
"""

import argparse
import hashlib
import html
import json
import logging
import re
import sys
import time
import urllib.parse
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Setup import path strictly within project
SCRIPT_PATH = Path(__file__).resolve()
ROOT_DIR = SCRIPT_PATH.parent.parent if SCRIPT_PATH.parent.name in ("scripts", "backend") else SCRIPT_PATH.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import fitz  # PyMuPDF
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.rag.cleaning import clean_document, remove_cross_document_boilerplate
from app.rag.ingestion import run_ingestion
from app.rag.parsing import ParsedDocument, parse_document, parse_html
from app.services.storage_service import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load_college")

# PII regex patterns for audit/filtering
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:(?:\+?91[\-\s]?)?[6-9]\d{9})(?!\d)")
ROLL_RE = re.compile(
    r"\b(?:0901[A-Za-z0-9]{6,12}|[A-Za-z]{2,6}\d{2}[A-Za-z]?\d{3,6})\b",
    re.IGNORECASE,
)
NAME_ROLL_RE = re.compile(
    r"\b[A-Za-z]{2,}(?:\s+[A-Za-z]{2,}){1,4}\s+(?:0901[A-Za-z0-9]{6,12}|[A-Za-z]{2,6}\d{2}[A-Za-z]?\d{3,6})\b",
    re.IGNORECASE,
)

EXCLUDE_KEYWORDS = [
    "marks",
    "time table",
    "attendance",
    "eligible",
    "debarred",
    "result",
    "merit list",
]

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_PDF_COUNT = 60
MAX_OTHER_COUNT = 10

DEFAULT_MANIFEST_PATH = ROOT_DIR / "data" / "raw" / "college" / "manifest.json"
DEFAULT_PAGES_DIR = ROOT_DIR / "data" / "raw" / "college" / "pages"
DEFAULT_PDFS_DIR = ROOT_DIR / "data" / "raw" / "college" / "pdfs"

GENERIC_TITLES = {
    "DEPARTMENT OF INFORMATION TECHNOLOGY",
    "SCHOOL OF INFORMATION TECHNOLOGY",
    "BOARD OF STUDIES (BOS)",
    "BOARD OF STUDIES",
    "BOS PROCEEDING",
    "BOS PROCEEDINGS",
    "MINUTES OF MEETING",
    "MINUTES OF THE MEETING",
    "PROCEEDINGS OF THE MEETING",
    "TABLE OF CONTENTS",
    "COURSE STRUCTURE",
    "CURRICULUM",
    "SYLLABUS",
    "SCHEME",
    "ANNEXURE",
    "STANDARD OPERATING PROCEDURE",
    "OUTCOME BASED",
    "STANDARD OPERATING",
}


def format_size(bytes_val: int) -> str:
    if bytes_val < 1024:
        return f"{bytes_val} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    else:
        return f"{bytes_val / (1024 * 1024):.2f} MB"


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(manifest_path: Path) -> tuple[dict[str, dict], set[str]]:
    """
    Loads manifest if it exists at manifest_path (e.g. data/raw/college/manifest.json).
    Never searches elsewhere. Returns:
      (lookup_map, manifest_filenames)
      where lookup_map is {filename: {"source_url": ..., "source_title": ...}}
      and manifest_filenames is the set of all filenames referenced in the manifest.
    """
    if not manifest_path.exists():
        return {}, set()

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Could not read manifest at %s: %s", manifest_path, e)
        return {}, set()

    lookup = {}
    manifest_filenames = set()

    items = []
    if isinstance(data, dict):
        pages = data.get("pages", [])
        assets = data.get("assets", [])
        if isinstance(pages, list):
            items.extend(pages)
        elif isinstance(pages, dict):
            items.extend(pages.values())
        if isinstance(assets, list):
            items.extend(assets)
        elif isinstance(assets, dict):
            items.extend(assets.values())
    elif isinstance(data, list):
        items.extend(data)

    for item in items:
        if not isinstance(item, dict):
            continue
        local_path = item.get("local_path") or item.get("filename") or ""
        fname = Path(local_path).name if local_path else ""
        if not fname:
            continue
        manifest_filenames.add(fname)
        url = item.get("url") or None
        raw_title = item.get("original_filename") or item.get("title") or item.get("source_title") or None
        title = html.unescape(raw_title).strip() if raw_title else None
        lookup[fname] = {
            "source_url": url,
            "source_title": title,
        }

    return lookup, manifest_filenames


def clean_images_filename(filename: str) -> str:
    """
    For files named images__...__X.pdf__hash.pdf, ALWAYS use the cleaned filename X:
    - URL-decode %20
    - strip .docx / .pdf extensions
    - replace underscores with spaces
    - strip the hash suffix
    """
    parts = filename.split("__")
    if len(parts) >= 2:
        last = parts[-1]
        last_clean = re.sub(r"(\.docx|\.pdf)+$", "", last, flags=re.IGNORECASE)
        if re.match(r"^[0-9a-f]{6,12}$", last_clean, re.IGNORECASE):
            target = parts[-2]
        else:
            target = parts[-1]
    else:
        target = filename

    target = re.sub(r"(\.docx|\.pdf)+$", "", target, flags=re.IGNORECASE)
    target = urllib.parse.unquote(target)
    target = target.replace("_", " ")
    target = re.sub(r"\s+", " ", target).strip()
    return html.unescape(target).strip() or filename


def clean_pdf_filename(filename: str) -> str:
    """
    Clean filename fallback:
    - For opaque names like uc__015ae44e.pdf -> 'College document 015ae4'
    - For files with __ (like images__...__X.pdf__hash.pdf) -> use clean_images_filename
    """
    if filename.startswith("uc__"):
        stem = filename[:-4] if filename.lower().endswith(".pdf") else filename
        hash_part = stem[4:]
        return f"College document {hash_part[:6]}"
    return clean_images_filename(filename)


def is_letterhead(line: str) -> bool:
    """
    Check if line is a letterhead line:
    - Contains "MADHAV INSTITUTE" or "MITS"
    - "GWALIOR" only
    - All-caps institute names or accreditation/affiliation headers
    """
    upper = line.upper()
    if "MADHAV INSTITUTE" in upper or "MITS" in upper:
        return True
    cleaned_letters = re.sub(r"[^A-Za-z]", "", upper)
    if "GWALIOR" in upper and (cleaned_letters == "GWALIOR" or len(cleaned_letters) <= 10):
        return True
    if any(term in upper for term in [
        "INSTITUTE OF TECHNOLOGY AND SCIENCE",
        "INSTITUTE OF TECHNOLOGY & SCIENCE",
        "DEEMED TO BE UNIVERSITY",
        "DEEMED UNIVERSITY",
        "A GOVT. AIDED UGC AUTONOMOUS",
    ]):
        return True
    return False


def is_generic_title(title: str) -> bool:
    cleaned = re.sub(r"[^A-Za-z\s]", "", title).strip().upper()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned in GENERIC_TITLES


def is_garbled(text: str) -> bool:
    if not text:
        return True
    valid_chars = sum(1 for c in text if (c.isascii() and (c.isalnum() or c.isspace())))
    return (valid_chars / len(text)) < 0.70


def extract_html_title(path: Path) -> str:
    """
    Extract HTML title from <title> tag, falling back to cleaned filename.
    Decodes HTML entities.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"<title[^>]*>(.*?)</title>", content, re.IGNORECASE | re.DOTALL)
        if match:
            raw_title = match.group(1).strip()
            title = html.unescape(raw_title)
            title = re.sub(r"\s+", " ", title).strip()
            if title:
                return title
    except Exception:
        pass
    return clean_images_filename(path.name)


def extract_pdf_title(path: Path, doc: Optional[fitz.Document] = None) -> str:
    """
    PDF title rule:
    1. For files named images__...__X.pdf__hash.pdf (or not starting with uc__),
       ALWAYS use the cleaned filename X.
    2. Only for opaque uc__hash.pdf files use the first non-letterhead line of page 1;
       if it is garbled, under 15 letters, or generic, use "College document <hash6>".
    """
    fn = path.name

    # Rule 1: files named images__ (or anything other than uc__) ALWAYS use cleaned filename X
    if not fn.startswith("uc__"):
        return clean_images_filename(fn)

    # Rule 2: opaque uc__ files
    stem = fn[:-4] if fn.lower().endswith(".pdf") else fn
    hash_part = stem[4:]
    fallback = f"College document {hash_part[:6]}"

    closed_here = False
    try:
        if doc is None:
            doc = fitz.open(str(path))
            closed_here = True

        if len(doc) > 0:
            page = doc[0]
            blocks = page.get_text("blocks")
            for b in blocks:
                if len(b) >= 5 and b[4]:
                    for line in b[4].splitlines():
                        cleaned = re.sub(r"\s+", " ", line).strip()
                        cleaned = cleaned.lstrip("•-–—*·\t ")
                        letters_count = sum(1 for c in cleaned if c.isalpha())
                        if letters_count >= 15:
                            if is_letterhead(cleaned):
                                continue
                            if re.match(r"^(https?://|www\.)", cleaned, re.IGNORECASE):
                                continue
                            if is_garbled(cleaned) or is_generic_title(cleaned):
                                return fallback
                            return html.unescape(cleaned).strip()
    except Exception:
        pass
    finally:
        if closed_here and doc is not None:
            doc.close()

    return fallback


def extract_file_suffix(filename: str) -> str:
    """
    Extract date or hash suffix from filename to disambiguate identical titles.
    """
    date_patterns = [
        r"(\b\d{1,2}[-_.\s](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_.\s]\d{2,4}\b)",
        r"(\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-_.\s]\d{4}\b)",
        r"(\b\d{4}[-_.]\d{1,2}[-_.]\d{1,2}\b)",
        r"(\b\d{1,2}[-_.]\d{1,2}[-_.]\d{2,4}\b)",
        r"(\b20\d{2}\b)",
    ]
    fn_decoded = urllib.parse.unquote(filename).replace("_", " ")
    for pat in date_patterns:
        m = re.search(pat, fn_decoded, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    hash_match = re.search(r"([0-9a-f]{6,12})(?:\.pdf)?$", filename, re.IGNORECASE)
    if hash_match:
        return hash_match.group(1)[:6]

    any_hash = re.search(r"([0-9a-f]{6,12})", filename, re.IGNORECASE)
    if any_hash:
        return any_hash.group(1)[:6]

    return "1"


def make_unique_titles(items: list[dict]) -> list[dict]:
    """
    Ensure all document titles in items are unique.
    Appends date or hash suffix if two documents share a title.
    """
    title_counts = Counter(item["title"] for item in items)
    duplicates = {t for t, c in title_counts.items() if c > 1}
    if not duplicates:
        return items

    seen = defaultdict(int)
    for item in items:
        t = item["title"]
        if t in duplicates:
            seen[t] += 1
            suffix = extract_file_suffix(item["filename"])
            if suffix and suffix not in t:
                item["title"] = f"{t} ({suffix})"
            else:
                item["title"] = f"{t} ({seen[t]})"

    title_counts2 = Counter(item["title"] for item in items)
    for item in items:
        t = item["title"]
        if title_counts2[t] > 1:
            h = re.search(r"([0-9a-f]{6,12})", item["filename"], re.IGNORECASE)
            suffix = h.group(1)[:6] if h else str(uuid.uuid4().hex[:6])
            item["title"] = f"{t} ({suffix})"
            title_counts2[t] -= 1

    return items


def is_sop_or_low_value(filename: str, title: str) -> bool:
    check = f"{filename} {title}".lower()
    return any(term in check for term in [
        "sop",
        "brochure",
        "banner",
        "co_po",
        "co-po",
        "co attainment",
        "po attainment",
        "po_attainment",
        "co_it",
        "po_it",
        "co_a_it",
        "cos ",
        "co-po attainment",
    ])


def build_syllabus_title(p1_text: str, filename: str) -> str:
    """
    Build syllabus title from page-1 text:
      e.g. programme + semester/year like 'B.Tech IT Syllabus, Semester 5'
      If nothing reliable, use 'Syllabus <hash6>'.
      Never use '(Under Flexible Curriculum)' alone.
    """
    hash_match = re.search(r"([0-9a-f]{6,12})", filename, re.IGNORECASE)
    hash6 = hash_match.group(1)[:6] if hash_match else "000000"
    fallback = f"Syllabus {hash6}"

    if not p1_text:
        return fallback

    # 1. Programme
    prog = None
    if re.search(r"\bB\.?\s*Tech\b", p1_text, re.IGNORECASE):
        prog = "B.Tech"
    elif re.search(r"\bM\.?\s*Tech\b", p1_text, re.IGNORECASE):
        prog = "M.Tech"
    elif re.search(r"\bMCA\b", p1_text):
        prog = "MCA"

    # 2. Specialization
    spec_parts = []
    if re.search(r"\bInformation\s+Technology\b|\bIT\b", p1_text, re.IGNORECASE):
        spec_parts.append("IT")

    if re.search(r"\bHonours?\b", p1_text, re.IGNORECASE):
        spec_parts.append("Honours")
    elif re.search(r"\bMinor\b", p1_text, re.IGNORECASE):
        spec_parts.append("Minor")

    # 3. Semester
    sem = None
    sem_m = re.search(r"\b(I{1,3}|IV|V|VI{1,3}|VIII|\d)(?:st|nd|rd|th)?\s*(?:Sem|Semester)\b", p1_text, re.IGNORECASE)
    roman_map = {
        "1": "1", "I": "1", "2": "2", "II": "2", "3": "3", "III": "3",
        "4": "4", "IV": "4", "5": "5", "V": "5", "6": "6", "VI": "6",
        "7": "7", "VII": "7", "8": "8", "VIII": "8",
    }
    if sem_m:
        raw_sem = sem_m.group(1).upper()
        sem_num = roman_map.get(raw_sem, raw_sem)
        sem = f"Semester {sem_num}"
    else:
        sem_m2 = re.search(r"\b(?:Sem|Semester)\s*[-:]?\s*(I{1,3}|IV|V|VI{1,3}|VIII|\d)\b", p1_text, re.IGNORECASE)
        if sem_m2:
            raw_sem = sem_m2.group(1).upper()
            sem_num = roman_map.get(raw_sem, raw_sem)
            sem = f"Semester {sem_num}"

    # 4. Year / Batch
    batch = None
    batch_m = re.search(
        r"\b(?:Admitted\s+Batch|Batch\s+Admitted\s+in|Session:?)\s*\(?(\d{4}[-–]\d{2,4})\)?",
        p1_text,
        re.IGNORECASE,
    )
    if batch_m:
        batch = batch_m.group(1).replace("–", "-")
    else:
        year_m = re.search(r"\((\d{4}[-–]\d{2,4})\)", p1_text)
        if year_m:
            batch = year_m.group(1).replace("–", "-")

    # 5. Assemble
    if prog:
        spec_str = " ".join(spec_parts) if spec_parts else "IT"
        base = f"{prog} {spec_str} Syllabus"
        if sem and batch:
            return f"{base}, {sem} ({batch})"
        elif sem:
            return f"{base}, {sem}"
        elif batch:
            return f"{base}, {batch}"
        return base
    elif spec_parts:
        spec_str = " ".join(spec_parts)
        base = f"{spec_str} Syllabus"
        if sem and batch:
            return f"{base}, {sem} ({batch})"
        elif sem:
            return f"{base}, {sem}"
        elif batch:
            return f"{base}, {batch}"
        return base

    return fallback


def categorize_pdf(title: str, filename: str, p1_text: str = "") -> str:
    check = f"{title} {filename}".lower().replace("_", " ")
    if "syllabus" in check or "curriculum" in check:
        return "syllabus"
    elif "scheme" in check:
        return "schemes"
    elif any(k in check for k in ("circular", "notification", "order", "notice")):
        return "circulars/notices"
    elif any(k in check for k in ("bos", "proceeding", "board of studies")):
        return "bos"
    elif "report" in check:
        return "reports"

    # Category rule: classify a PDF as syllabus if page-1 text or title contains
    # "syllabus", "curriculum", "course contents", "semester" with course codes,
    # or "Departmental Core"; do this BEFORE the "other" bucket.
    if not is_sop_or_low_value(filename, title):
        p1_lower = p1_text.lower()
        has_sem_with_course_codes = bool(
            re.search(r"\b(?:sem|semester)\b", p1_lower)
            and re.search(r"\b(?:[a-z]{2,4}\s*[-]?\s*\d{3,6}|\d{6}|course\s*code)\b", p1_lower)
        )
        if (
            "syllabus" in p1_lower
            or "curriculum" in p1_lower
            or "course contents" in p1_lower
            or "departmental core" in p1_lower
            or has_sem_with_course_codes
        ):
            return "syllabus"

    return "other"


def select_college_corpus(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    pages_dir: Path = DEFAULT_PAGES_DIR,
    pdfs_dir: Path = DEFAULT_PDFS_DIR,
    max_pdfs: int = MAX_PDF_COUNT,
) -> tuple[list[dict], list[dict], dict[str, int], dict]:
    """
    Select actual HTML pages and up to max_pdfs filtered TEXT-class PDFs from disk.
    Priority order: syllabus, schemes, circulars/notices, BoS, reports, then other (max 10).
    Captures excluded priority candidates for review.
    Returns: (selected_html, selected_pdfs, excluded_counts, stats)
    """
    manifest_lookup, manifest_filenames = load_manifest(manifest_path)

    # 1. Enumerate ACTUAL files on disk only
    html_files = sorted(list(pages_dir.glob("*.html")) + list(pages_dir.glob("*.htm"))) if pages_dir.exists() else []
    pdf_files = sorted(list(pdfs_dir.glob("*.pdf"))) if pdfs_dir.exists() else []

    disk_filenames = {f.name for f in html_files} | {f.name for f in pdf_files}
    manifest_not_on_disk = len(manifest_filenames - disk_filenames)
    disk_without_manifest = len(disk_filenames - manifest_filenames)

    # 2. HTML selection
    selected_html = []
    seen_html_names = set()
    for hf in html_files:
        if hf.name in seen_html_names:
            continue
        seen_html_names.add(hf.name)
        meta = manifest_lookup.get(hf.name, {})
        url = meta.get("source_url")
        raw_title = meta.get("source_title") or extract_html_title(hf)
        title = html.unescape(raw_title).strip()
        size = hf.stat().st_size
        selected_html.append({
            "type": "html",
            "path": hf,
            "filename": hf.name,
            "title": title,
            "url": url,
            "size": size,
            "pages": None,
        })

    # 3. PDF selection & filtering
    selected_pdfs = []
    excluded_counts = {
        "exceeds_size": 0,
        "not_text": 0,
        "excluded_keyword": 0,
        "has_roll": 0,
        "too_many_pii": 0,
    }

    excluded_priority_candidates = []
    excluded_roll_candidates = []
    candidates = []
    seen_eval_filenames = set()

    for pf in pdf_files:
        if pf.name in seen_eval_filenames:
            continue
        seen_eval_filenames.add(pf.name)

        size = pf.stat().st_size
        meta = manifest_lookup.get(pf.name, {})
        url = meta.get("source_url")

        # Extract title per Rule 1:
        # images__ ALWAYS uses clean_images_filename; uc__ uses page 1 heading or fallback
        doc = None
        page_count = 0
        p1_sample = ""
        try:
            doc = fitz.open(str(pf))
            page_count = len(doc)
            if page_count > 0:
                p1_sample = doc[0].get_text()
            raw_title = meta.get("source_title") or extract_pdf_title(pf, doc)
            title = html.unescape(raw_title).strip()
        except Exception:
            raw_title = meta.get("source_title") or clean_pdf_filename(pf.name)
            title = html.unescape(raw_title).strip()

        cat = categorize_pdf(title, pf.name, p1_sample)
        if cat == "syllabus":
            if pf.name.startswith("uc__") or is_generic_title(title) or "Under Flexible Curriculum" in title:
                syl_title = build_syllabus_title(p1_sample, pf.name)
                if syl_title:
                    title = syl_title
        elif "Under Flexible Curriculum" in title or title.strip() == "(Under Flexible Curriculum)":
            title = build_syllabus_title(p1_sample, pf.name)

        is_priority = cat in ("syllabus", "schemes", "circulars/notices")

        # Check title and first page for roll pattern or person's name + roll number
        p1_roll_match = ROLL_RE.search(p1_sample) or NAME_ROLL_RE.search(p1_sample)
        title_roll_match = ROLL_RE.search(title) or NAME_ROLL_RE.search(title)
        if p1_roll_match or title_roll_match:
            excluded_counts["has_roll"] += 1
            roll_count = len(ROLL_RE.findall(p1_sample)) + (1 if title_roll_match else 0)
            excluded_roll_candidates.append({
                "filename": pf.name,
                "title": title,
                "roll_count": max(roll_count, 1),
            })
            if is_priority:
                excluded_priority_candidates.append({
                    "filename": pf.name,
                    "title": title,
                    "category": cat,
                    "reason": f"has_roll ({roll_count} roll lines)",
                })
            if doc is not None:
                doc.close()
            continue

        # Rule 1: <= 25 MB
        if size > MAX_FILE_BYTES:
            excluded_counts["exceeds_size"] += 1
            if is_priority:
                excluded_priority_candidates.append({
                    "filename": pf.name,
                    "title": title,
                    "category": cat,
                    "reason": f"exceeds_size ({size / (1024 * 1024):.1f} MB > 25 MB)",
                })
            if doc is not None:
                doc.close()
            continue

        # Rule 2: Exclude names/titles containing forbidden keywords
        name_check = f"{pf.name} {title}".lower().replace("_", " ")
        kw_found = [kw for kw in EXCLUDE_KEYWORDS if kw in name_check]
        if kw_found:
            excluded_counts["excluded_keyword"] += 1
            if is_priority:
                excluded_priority_candidates.append({
                    "filename": pf.name,
                    "title": title,
                    "category": cat,
                    "reason": f"excluded_keyword ('{kw_found[0]}')",
                })
            if doc is not None:
                doc.close()
            continue

        # Rule 3: Text classification (>= 200 chars/page)
        try:
            parsed = parse_document(pf, "pdf")
            cleaned = clean_document(parsed)
            total_chars = sum(len(b.text) for b in cleaned.blocks)
            avg_chars = total_chars / page_count if page_count > 0 else 0
        except Exception:
            total_chars = 0
            avg_chars = 0
            parsed = None

        if doc is not None:
            doc.close()

        if avg_chars < 200 or parsed is None:
            excluded_counts["not_text"] += 1
            if is_priority:
                excluded_priority_candidates.append({
                    "filename": pf.name,
                    "title": title,
                    "category": cat,
                    "reason": f"not_text ({avg_chars:.1f} avg chars/page < 200)",
                })
            continue

        # Rule 4: Zero roll numbers, < 5 emails or phones
        raw_text = "\n".join(b.text for b in parsed.blocks)
        roll_lines = sum(1 for line in raw_text.splitlines() if ROLL_RE.search(line))
        if roll_lines > 0:
            excluded_counts["has_roll"] += 1
            roll_count = len(ROLL_RE.findall(raw_text))
            excluded_roll_candidates.append({
                "filename": pf.name,
                "title": title,
                "roll_count": max(roll_count, roll_lines, 1),
            })
            if is_priority:
                excluded_priority_candidates.append({
                    "filename": pf.name,
                    "title": title,
                    "category": cat,
                    "reason": f"has_roll ({roll_lines} roll lines)",
                })
            continue

        email_lines = sum(1 for line in raw_text.splitlines() if EMAIL_RE.search(line))
        phone_lines = sum(1 for line in raw_text.splitlines() if PHONE_RE.search(line))
        if email_lines >= 5 or phone_lines >= 5:
            excluded_counts["too_many_pii"] += 1
            if is_priority:
                excluded_priority_candidates.append({
                    "filename": pf.name,
                    "title": title,
                    "category": cat,
                    "reason": f"too_many_pii ({email_lines} email lines, {phone_lines} phone lines)",
                })
            continue

        candidates.append({
            "type": "pdf",
            "path": pf,
            "filename": pf.name,
            "title": title,
            "url": url,
            "size": size,
            "pages": page_count,
            "category": cat,
            "total_chars": total_chars,
        })

    # Selection fill priority:
    # 1. syllabus, schemes, circulars/notices, BoS, reports
    # 2. other capped at 10 files total, preferring most text and non-low-value
    categorized = defaultdict(list)
    for c in candidates:
        categorized[c["category"]].append(c)

    final_pdf_selection = []
    seen_selected_names = set()

    # Step A: Take high-priority categories in order
    priority_order = ["syllabus", "schemes", "circulars/notices", "bos", "reports"]
    for cat in priority_order:
        for item in sorted(categorized[cat], key=lambda x: (-x.get("total_chars", 0), x["filename"])):
            if item["filename"] not in seen_selected_names:
                seen_selected_names.add(item["filename"])
                final_pdf_selection.append(item)
                if len(final_pdf_selection) >= max_pdfs:
                    break
        if len(final_pdf_selection) >= max_pdfs:
            break

    # Step B: Add "other" capped at 10 files total
    # Prefer most text and non-low-value (never fill with SOP/brochure/banner/CO-PO unless < 60 better files)
    if len(final_pdf_selection) < max_pdfs:
        other_candidates = categorized["other"]
        other_sorted = sorted(
            other_candidates,
            key=lambda x: (
                is_sop_or_low_value(x["filename"], x["title"]),
                -x.get("total_chars", 0),
                x["filename"],
            ),
        )

        other_added = 0
        for item in other_sorted:
            if other_added >= MAX_OTHER_COUNT or len(final_pdf_selection) >= max_pdfs:
                break
            if item["filename"] not in seen_selected_names:
                seen_selected_names.add(item["filename"])
                final_pdf_selection.append(item)
                other_added += 1

    # Step C: Make titles unique
    final_pdf_selection = make_unique_titles(final_pdf_selection)
    selected_pdfs = final_pdf_selection

    stats = {
        "html_on_disk": len(html_files),
        "pdf_on_disk": len(pdf_files),
        "total_on_disk": len(html_files) + len(pdf_files),
        "manifest_not_on_disk": manifest_not_on_disk,
        "disk_without_manifest": disk_without_manifest,
        "eligible_pdfs": len(candidates),
        "excluded_priority_candidates": excluded_priority_candidates,
        "excluded_roll_candidates": excluded_roll_candidates,
    }

    return selected_html, selected_pdfs, excluded_counts, stats


def run_dry_run(
    selected_html: list[dict],
    selected_pdfs: list[dict],
    excluded_counts: dict[str, int],
    stats: Optional[dict] = None,
) -> None:
    print("=" * 80)
    print("COLLEGE CORPUS LOADER — DRY RUN (No DB / Qdrant changes)")
    print("=" * 80)

    if stats:
        print("\n1. FILES ON DISK:")
        print("-" * 80)
        print(f"  - HTML pages on disk:             {stats.get('html_on_disk', len(selected_html))}")
        print(f"  - PDF files on disk:              {stats.get('pdf_on_disk', len(selected_pdfs))}")
        print(f"  - Total files on disk:            {stats.get('total_on_disk', len(selected_html) + len(selected_pdfs))}")

        print("\n2. MANIFEST RECONCILIATION:")
        print("-" * 80)
        print(f"  - Entries in manifest but not on disk:     {stats.get('manifest_not_on_disk', 0)}")
        print(f"  - Files on disk without a manifest entry:  {stats.get('disk_without_manifest', 0)}")

    print(f"\n3. HTML WEBPAGES SELECTED ({len(selected_html)} files):")
    print("-" * 80)
    print(f"{'#':<3} {'Size':<10} {'Title / Filename'}")
    print("-" * 80)
    for i, h in enumerate(selected_html, start=1):
        print(f"{i:<3} {format_size(h['size']):<10} {h['title']}")
        print(f"    ↳ File: {h['filename']} | URL: {h['url'] or 'N/A'}")

    print(f"\n4. PDF DOCUMENTS SELECTED ({len(selected_pdfs)} files, capped at {MAX_PDF_COUNT}):")
    print("-" * 80)
    print(f"{'#':<3} {'Pages':<6} {'Size':<10} {'Category':<18} {'Title / Filename'}")
    print("-" * 80)
    for i, p in enumerate(selected_pdfs, start=1):
        print(f"{i:<3} {p['pages']:<6} {format_size(p['size']):<10} {p.get('category', ''):<18} {p['title']}")
        print(f"    ↳ File: {p['filename']} | URL: {p['url'] or 'N/A'}")

    print("\n" + "=" * 80)
    print("SELECTION SUMMARY:")
    print(f"  - Total HTML pages selected:      {len(selected_html)}")
    print(f"  - Total PDFs selected:            {len(selected_pdfs)}")
    print(f"  - Total files to ingest:          {len(selected_html) + len(selected_pdfs)}")

    print("\nEXCLUDED PDFS BREAKDOWN:")
    for reason, count in excluded_counts.items():
        print(f"  - {reason:<20}: {count} files")

    excluded_priority = stats.get("excluded_priority_candidates", []) if stats else []
    print("\n" + "=" * 80)
    print(f"EXCLUDED CANDIDATE SYLLABUS / SCHEME / CIRCULAR / NOTICE PDFS ({len(excluded_priority)} files):")
    print("-" * 80)
    if excluded_priority:
        print(f"{'#':<3} {'Category':<18} {'Title / Filename'}")
        print(f"    ↳ {'Exclusion Reason (PII line counts only, no values)'}")
        print("-" * 80)
        for i, item in enumerate(excluded_priority, start=1):
            print(f"{i:<3} {item['category']:<18} {item['title']}")
            print(f"    ↳ File: {item['filename']} | Reason: {item['reason']}")
    else:
        print("  None. No candidate syllabus, scheme, or circular PDFs were excluded.")

    excluded_rolls = stats.get("excluded_roll_candidates", []) if stats else []
    print("\n" + "=" * 80)
    print(f"FILES EXCLUDED FOR ROLL PATTERNS ({len(excluded_rolls)} files):")
    print("-" * 80)
    if excluded_rolls:
        print(f"{'#':<3} {'Roll Count':<12} {'Title / Filename'}")
        print("-" * 80)
        for i, item in enumerate(excluded_rolls, start=1):
            print(f"{i:<3} {item['roll_count']:<12} {item['title']}")
            print(f"    ↳ File: {item['filename']} | Counts only (no PII printed)")
    else:
        print("  None. No files were excluded for roll patterns.")

    if stats:
        total_excluded_pdfs = sum(excluded_counts.values())
        print("\n" + "=" * 80)
        print("NOTE ON TOTAL COUNTS:")
        print(
            f"  Why selected ({len(selected_pdfs)}) + excluded ({total_excluded_pdfs}) "
            f"is less than total PDFs on disk ({stats.get('pdf_on_disk', 0)}): "
            f"eligible 'other' candidates are capped at {MAX_OTHER_COUNT} (leaving {stats.get('eligible_pdfs', 0) - len(selected_pdfs)} eligible PDFs unselected)."
        )

    print("=" * 80)
    print("DRY RUN FINISHED. No database or vector operations performed.")
    print("=" * 80)


def get_or_create_college_workspace(db: Session, user: User) -> Workspace:
    membership = (
        db.query(WorkspaceMember)
        .join(Workspace)
        .filter(Workspace.name == "College", WorkspaceMember.user_id == user.id)
        .first()
    )
    if membership:
        logger.info("Found existing 'College' workspace (id=%s).", membership.workspace_id)
        return membership.workspace

    ws = db.query(Workspace).filter(Workspace.name == "College", Workspace.owner_id == user.id).first()
    if ws:
        logger.info("Found existing owned 'College' workspace (id=%s).", ws.id)
        return ws

    ws = Workspace(name="College", owner_id=user.id)
    db.add(ws)
    db.flush()

    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner")
    db.add(member)
    db.commit()
    db.refresh(ws)
    logger.info("Created new 'College' workspace (id=%s).", ws.id)
    return ws


def run_apply(
    user_email: str,
    selected_html: list[dict],
    selected_pdfs: list[dict],
) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            print(f"Error: User with email '{user_email}' not found. Never create users or print passwords.")
            sys.exit(1)

        workspace = get_or_create_college_workspace(db, user)
        print("=" * 80)
        print(f"COLLEGE CORPUS LOADER — APPLYING TO WORKSPACE 'College' (ID: {workspace.id})")
        print(f"User: {user.email}")
        print("=" * 80)

        # Pre-parse HTML files and remove cross-document boilerplate
        print("\n[Step 1/2] Processing HTML corpus (parsing + cross-document boilerplate removal)...")
        parsed_html_records = []
        for h in selected_html:
            doc = parse_html(h["path"])
            parsed_html_records.append((h, doc))

        docs_only = [item[1] for item in parsed_html_records]
        cleaned_html_docs = remove_cross_document_boilerplate(docs_only)

        ingested_count = 0
        skipped_count = 0
        failed_count = 0
        total_chunks = 0

        # Ingest HTML files
        print(f"\n[Step 2/2] Ingesting {len(selected_html)} HTML pages and {len(selected_pdfs)} PDFs...")
        for (h, _), cleaned_doc in zip(parsed_html_records, cleaned_html_docs):
            t0 = time.monotonic()
            file_bytes = h["path"].read_bytes()
            c_hash = compute_sha256(file_bytes)

            existing = (
                db.query(Document)
                .filter(Document.workspace_id == workspace.id, Document.content_hash == c_hash)
                .first()
            )
            if existing:
                skipped_count += 1
                print(f"  [HTML] {h['title'][:40]:<40} | SKIPPED (duplicate content_hash) | 0.00s")
                continue

            try:
                storage_path = storage.save(file_bytes, "html")
                doc_record = Document(
                    workspace_id=workspace.id,
                    uploaded_by=user.id,
                    filename=h["filename"],
                    file_type="html",
                    storage_path=storage_path,
                    file_size=len(file_bytes),
                    content_hash=c_hash,
                    source_url=h["url"],
                    source_title=h["title"],
                    status=DocumentStatus.PENDING,
                )
                db.add(doc_record)
                db.commit()
                db.refresh(doc_record)

                run_ingestion(
                    doc_record.id,
                    db,
                    str(storage.open(doc_record.storage_path)),
                    pre_parsed_doc=cleaned_doc,
                )
                db.refresh(doc_record)
                dur = time.monotonic() - t0

                if doc_record.status == DocumentStatus.COMPLETED:
                    ingested_count += 1
                    total_chunks += doc_record.chunk_count or 0
                    print(f"  [HTML] {h['title'][:40]:<40} | COMPLETED | {doc_record.chunk_count or 0} chunks | {dur:.2f}s")
                else:
                    failed_count += 1
                    print(f"  [HTML] {h['title'][:40]:<40} | FAILED ({doc_record.error_message}) | {dur:.2f}s")
            except Exception as e:
                db.rollback()
                failed_count += 1
                print(f"  [HTML] {h['title'][:40]:<40} | ERROR ({e}) | {time.monotonic() - t0:.2f}s")

        # Ingest PDF files
        for p in selected_pdfs:
            t0 = time.monotonic()
            file_bytes = p["path"].read_bytes()
            c_hash = compute_sha256(file_bytes)

            existing = (
                db.query(Document)
                .filter(Document.workspace_id == workspace.id, Document.content_hash == c_hash)
                .first()
            )
            if existing:
                skipped_count += 1
                print(f"  [PDF]  {p['title'][:40]:<40} | SKIPPED (duplicate content_hash) | 0.00s")
                continue

            try:
                storage_path = storage.save(file_bytes, "pdf")
                doc_record = Document(
                    workspace_id=workspace.id,
                    uploaded_by=user.id,
                    filename=p["filename"],
                    file_type="pdf",
                    storage_path=storage_path,
                    file_size=len(file_bytes),
                    content_hash=c_hash,
                    source_url=p["url"],
                    source_title=p["title"],
                    status=DocumentStatus.PENDING,
                )
                db.add(doc_record)
                db.commit()
                db.refresh(doc_record)

                run_ingestion(
                    doc_record.id,
                    db,
                    str(storage.open(doc_record.storage_path)),
                )
                db.refresh(doc_record)
                dur = time.monotonic() - t0

                if doc_record.status == DocumentStatus.COMPLETED:
                    ingested_count += 1
                    total_chunks += doc_record.chunk_count or 0
                    print(f"  [PDF]  {p['title'][:40]:<40} | COMPLETED | {doc_record.chunk_count or 0} chunks | {dur:.2f}s")
                else:
                    failed_count += 1
                    print(f"  [PDF]  {p['title'][:40]:<40} | FAILED ({doc_record.error_message}) | {dur:.2f}s")
            except Exception as e:
                db.rollback()
                failed_count += 1
                print(f"  [PDF]  {p['title'][:40]:<40} | ERROR ({e}) | {time.monotonic() - t0:.2f}s")

        print("\n" + "=" * 80)
        print("COLLEGE CORPUS INGESTION SUMMARY:")
        print(f"  - Ingested files:  {ingested_count}")
        print(f"  - Skipped (dups):  {skipped_count}")
        print(f"  - Failed files:    {failed_count}")
        print(f"  - Total chunks:    {total_chunks}")
        print("=" * 80)

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="College Corpus Loader")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform dry-run selection only")
    parser.add_argument("--apply", action="store_true", default=False, help="Apply ingestion into workspace")
    parser.add_argument("--user-email", type=str, help="Email of user owning the College workspace (required for --apply)")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH, help="Path to manifest.json (optional)")
    parser.add_argument("--pages-dir", type=Path, default=DEFAULT_PAGES_DIR, help="Path to HTML pages")
    parser.add_argument("--pdfs-dir", type=Path, default=DEFAULT_PDFS_DIR, help="Path to college PDFs")

    args = parser.parse_args()

    selected_html, selected_pdfs, excluded_counts, stats = select_college_corpus(
        manifest_path=args.manifest,
        pages_dir=args.pages_dir,
        pdfs_dir=args.pdfs_dir,
    )

    if args.apply:
        if not args.user_email:
            print("Error: --user-email is required when running with --apply.")
            sys.exit(1)
        run_apply(args.user_email, selected_html, selected_pdfs)
    else:
        run_dry_run(selected_html, selected_pdfs, excluded_counts, stats)


if __name__ == "__main__":
    main()
