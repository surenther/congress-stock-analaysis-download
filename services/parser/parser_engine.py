#!/usr/bin/env python3
"""
Congressional Disclosure Document Parsing & OCR Engine

Reads raw filings stored on the external host volume mounted at ``/data`` and
produces a standardized JSON document per filing under
``/data/parsed_json/{doc_id}.json``.

Two input formats are supported:

* **Senate HTML** filings (``/data/senate/.../*.html`` / ``*.htm``) — parsed
  with BeautifulSoup4/lxml.
* **House PDF** filings (``/data/house_rep/.../*.pdf``) — parsed with
  ``pdfplumber`` for digital PDFs, falling back to ``pdf2image`` +
  ``pytesseract`` OCR for scanned/image-based disclosures.

Storage hierarchy produced by the downloader service::

    {OUTPUT_BASE_DIR}/{OUTPUT_DIR}/{YEAR}/{Month filed}/{Name}/{doc_id}.pdf|.html

Standardized output schema::

    {
      "doc_id": "10073198",
      "chamber": "House",
      "filer_name": "Laurie Buckhout",
      "filing_date": "2026-01-24",
      "report_type": "PTR",
      "transactions": [
        {
          "ticker": "NVDA",
          "asset_name": "NVIDIA Corporation",
          "tx_type": "Purchase",
          "tx_date": "2026-01-15",
          "amount_range": "$15,001 - $50,000"
        }
      ]
    }
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Maps a logical chamber name to the on-disk subfolder written by the downloader.
CHAMBER_DIRS = {"house": "house_rep", "senate": "senate"}

# Human-readable chamber label stored in the parsed JSON.
CHAMBER_LABELS = {"house": "House", "senate": "Senate"}

# Destination subfolder (relative to OUTPUT_BASE_DIR) for the parsed JSON files.
PARSED_JSON_DIRNAME = "parsed_json"

# Header phrases that mark a filing as an extension request rather than a
# transactional disclosure. When present on page 1 of a House PDF the parser
# records ``report_type: "Extension"`` and skips table extraction entirely.
EXTENSION_MARKERS = ("EXTENSION REQUEST FORM", "COMMITTEE ON ETHICS")

# House filing-type code -> human-readable report type.
HOUSE_FILING_TYPE_MAP = {
    "P": "PTR",
    "A": "Annual",
    "O": "Annual",
    "C": "Candidate",
    "T": "Termination",
    "Z": "Amendment",
}

# Minimum number of characters we expect from a digital (text) PDF page before
# we consider the document scanned and switch to the OCR fallback.
MIN_DIGITAL_TEXT_CHARS = 50


def get_base_output_dir() -> Path:
    """Return the root storage directory (the mounted host volume)."""
    base = os.getenv("OUTPUT_BASE_DIR", "/data")
    return Path(base) if base else Path("/data")


def get_parsed_json_dir() -> Path:
    """Return the directory where parsed JSON documents are written."""
    return get_base_output_dir() / PARSED_JSON_DIRNAME


# ==============================================================================
# NORMALIZATION HELPERS
# ==============================================================================

def normalize_tx_type(raw: str) -> str:
    """Normalize a raw transaction-type cell to ``Purchase`` or ``Sale``."""
    if not raw:
        return ""
    value = raw.strip()
    lowered = value.lower()

    if "purchase" in lowered or "buy" in lowered or "bought" in lowered:
        return "Purchase"
    if "sale" in lowered or "sell" in lowered or "sold" in lowered:
        return "Sale"
    if lowered in ("p", "purchase"):
        return "Purchase"
    if lowered in ("s", "sale"):
        return "Sale"
    return value


def normalize_date(raw: str) -> str:
    """Normalize a date string to ISO ``YYYY-MM-DD`` where possible."""
    if not raw:
        return ""
    value = raw.strip()

    for fmt in (
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%m-%d-%Y",
        "%d/%m/%Y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    match = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", value)
    if match:
        month, day, year = match.groups()
        if len(year) == 2:
            year = f"20{year}"
        try:
            return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return value


def extract_ticker(asset_name: str) -> str:
    """Best-effort extraction of a stock ticker from an asset description.

    Handles the two dominant congressional disclosure conventions:
      * ``NVIDIA Corporation (NVDA)`` — parenthesised symbol.
      * ``NVIDIA Corp - Common Stock (NVDA) [ST]`` — symbol + asset-type tag.
    """
    if not asset_name:
        return ""

    match = re.search(r"\(([A-Z]{1,6}(?:\.[A-Z]{1,3})?)\)", asset_name)
    if match:
        return match.group(1)

    match = re.search(r"\b([A-Z]{1,5})\b\s*\[(?:ST|OP|CS|ET|MF|FI)\]", asset_name)
    if match:
        return match.group(1)

    return ""


def _map_columns(header: List[str]) -> Dict[str, int]:
    """Map a table header row to logical transaction field indices."""
    col_map: Dict[str, int] = {}
    for index, cell in enumerate(header):
        label = (cell or "").strip().lower()
        if not label:
            continue
        if "ticker" in label or "symbol" in label:
            col_map.setdefault("ticker", index)
        elif "asset" in label and "type" not in label:
            col_map.setdefault("asset_name", index)
        elif "type" in label and "asset" not in label:
            col_map.setdefault("tx_type", index)
        elif "date" in label and "notification" not in label:
            col_map.setdefault("tx_date", index)
        elif "amount" in label or "value" in label:
            col_map.setdefault("amount_range", index)
    return col_map


def _build_transaction(cells: List[str], col_map: Dict[str, int]) -> Optional[Dict[str, str]]:
    """Build a single transaction dict from a table row using the column map."""

    def get(field: str) -> str:
        idx = col_map.get(field)
        if idx is None or idx >= len(cells):
            return ""
        return (cells[idx] or "").strip()

    asset = get("asset_name")
    ticker = get("ticker") or extract_ticker(asset)
    tx_type = normalize_tx_type(get("tx_type"))
    tx_date = normalize_date(get("tx_date"))
    amount = get("amount_range")

    if not asset and not ticker and not amount:
        return None

    return {
        "ticker": ticker,
        "asset_name": asset,
        "tx_type": tx_type,
        "tx_date": tx_date,
        "amount_range": amount,
    }


def _rows_to_transactions(rows: List[List[str]]) -> List[Dict[str, str]]:
    """Convert a matrix of table rows (header + data) into transactions."""
    if not rows or len(rows) < 2:
        return []

    header = [(c or "").strip() for c in rows[0]]
    col_map = _map_columns(header)

    # A usable transaction table must expose at least an asset or type column.
    if "asset_name" not in col_map and "tx_type" not in col_map:
        return []

    transactions: List[Dict[str, str]] = []
    for row in rows[1:]:
        cells = [(c or "").strip() for c in row]
        tx = _build_transaction(cells, col_map)
        if tx:
            transactions.append(tx)
    return transactions


# ==============================================================================
# PATH-DERIVED METADATA
# ==============================================================================

def _chamber_from_path(path: Path) -> str:
    """Infer the logical chamber (``house``/``senate``) from a file path."""
    for part in path.parts:
        if part == CHAMBER_DIRS["house"]:
            return "house"
        if part == CHAMBER_DIRS["senate"]:
            return "senate"
    return "house"


def _name_from_dir(name_dir: str) -> str:
    """Convert a ``Last_First`` directory name to ``First Last``.

    The downloader writes directories using the ``last_first`` convention
    (e.g. ``Buckhout_Laurie``). Extra middle-name tokens are preserved after the
    first name (e.g. ``Last_First_Middle`` -> ``First Middle Last``).
    """
    if not name_dir:
        return ""
    tokens = [t for t in name_dir.split("_") if t]
    if len(tokens) >= 2:
        return " ".join(tokens[1:] + [tokens[0]])
    return name_dir


def _metadata_from_path(path: Path) -> Dict[str, str]:
    """Derive doc_id/year/month/filer_name from the downloader's folder layout."""
    parts = path.parts
    doc_id = path.stem
    year = ""
    month_dir = ""
    name_dir = ""

    for index, part in enumerate(parts):
        if part in CHAMBER_DIRS.values():
            if index + 1 < len(parts):
                year = parts[index + 1]
            if index + 2 < len(parts):
                month_dir = parts[index + 2]
            if index + 3 < len(parts):
                name_dir = parts[index + 3]
            break

    return {
        "doc_id": doc_id,
        "year": year,
        "month_dir": month_dir,
        "filer_name": _name_from_dir(name_dir),
    }


def _filing_date_from_text(text: str, year: str, month_dir: str) -> str:
    """Extract the filing date from free text, with a year/month fallback."""
    if text:
        patterns = (
            r"Filing\s*Date\s*[:\-]?\s*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
            r"Date\s*Filed\s*[:\-]?\s*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
            r"Filed\s*[:\-]?\s*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4})",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                normalized = normalize_date(match.group(1))
                if normalized:
                    return normalized

    # Fallback: reconstruct from the ``{YEAR}/{Month}`` directory components.
    month_match = re.match(r"(\d{1,2})", month_dir or "")
    if year and month_match:
        try:
            return datetime(int(year), int(month_match.group(1)), 1).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return ""


# ==============================================================================
# SENATE HTML PARSER
# ==============================================================================

def _extract_senate_name(soup, text: str, fallback: str) -> str:
    """Extract the Senator's name from the HTML header, falling back to path."""
    patterns = (
        r"Senator\s*[:\-]\s*([A-Z][A-Za-z\.'\-]+(?:\s+[A-Z][A-Za-z\.'\-]+){0,4})",
        r"Name\s*[:\-]\s*([A-Z][A-Za-z\.'\-]+(?:\s+[A-Z][A-Za-z\.'\-]+){0,4})",
        r"Hon\.\s*([A-Z][A-Za-z\.'\-]+(?:\s+[A-Z][A-Za-z\.'\-]+){0,4})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()

    for tag in soup.find_all(["h1", "h2", "title"]):
        candidate = tag.get_text(" ", strip=True)
        if candidate and re.search(r"[A-Za-z]", candidate):
            cleaned = re.sub(r"^(Periodic Transaction Report|Annual Report)\s*[-–:]\s*", "", candidate, flags=re.IGNORECASE)
            if cleaned and len(cleaned.split()) <= 6:
                return cleaned.strip()

    return fallback


def _detect_senate_report_type(text: str) -> str:
    """Classify a Senate filing as PTR / Annual / Amendment."""
    upper = text.upper()
    if "AMEND" in upper:
        return "Amendment"
    if "PERIODIC TRANSACTION" in upper or "TRANSACTION REPORT" in upper:
        return "PTR"
    if "ANNUAL REPORT" in upper:
        return "Annual"
    return "PTR"


def parse_senate_html(path: Path) -> Dict[str, Any]:
    """Parse a Senate HTML filing into the standardized document schema."""
    from bs4 import BeautifulSoup

    html = path.read_text(encoding="utf-8", errors="ignore")
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    text = soup.get_text("\n", strip=True)
    meta = _metadata_from_path(path)

    filer_name = _extract_senate_name(soup, text, meta["filer_name"])
    filing_date = _filing_date_from_text(text, meta["year"], meta["month_dir"])
    report_type = _detect_senate_report_type(text)

    transactions: List[Dict[str, str]] = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append(cells)
        transactions.extend(_rows_to_transactions(rows))

    # De-duplicate identical rows while preserving order.
    seen = set()
    unique_transactions = []
    for tx in transactions:
        key = tuple(sorted(tx.items()))
        if key not in seen:
            seen.add(key)
            unique_transactions.append(tx)

    return {
        "doc_id": meta["doc_id"],
        "chamber": "Senate",
        "filer_name": filer_name,
        "filing_date": filing_date,
        "report_type": report_type,
        "transactions": unique_transactions,
    }


# ==============================================================================
# HOUSE PDF PARSER (digital + OCR fallback)
# ==============================================================================

def _ocr_pdf(path: Path) -> List[str]:
    """Render a PDF to images and OCR each page with Tesseract."""
    from pdf2image import convert_from_path
    import pytesseract

    images = convert_from_path(str(path), dpi=300)
    return [pytesseract.image_to_string(image) for image in images]


def _extract_pdf_text(path: Path) -> List[str]:
    """Extract text page-by-page, falling back to OCR for scanned documents."""
    pages: List[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception:
        pages = []

    total_chars = sum(len(p.strip()) for p in pages)
    if total_chars < MIN_DIGITAL_TEXT_CHARS:
        try:
            ocr_pages = _ocr_pdf(path)
            if ocr_pages and sum(len(p.strip()) for p in ocr_pages) > total_chars:
                pages = ocr_pages
        except Exception:
            # OCR tooling unavailable (e.g. running outside the container) —
            # keep whatever digital text we managed to extract.
            pass

    return pages


def _extract_pdf_tables(path: Path) -> List[List[List[str]]]:
    """Extract grid/table structures from a digital PDF using pdfplumber."""
    tables: List[List[List[str]]] = []
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    tables.append(table)
    except Exception:
        tables = []
    return tables


def _transactions_from_text(text: str) -> List[Dict[str, str]]:
    """Regex fallback that pulls transactions from OCR/plain text lines."""
    transactions: List[Dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        amount_match = re.search(r"(\$[\d,]+\s*[-–]\s*\$[\d,]+)", line)
        if not amount_match:
            continue

        ticker = extract_ticker(line)
        date_match = re.search(r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})", line)
        tx_type = normalize_tx_type(line)

        transactions.append(
            {
                "ticker": ticker,
                "asset_name": line,
                "tx_type": tx_type if tx_type in ("Purchase", "Sale") else "",
                "tx_date": normalize_date(date_match.group(1)) if date_match else "",
                "amount_range": amount_match.group(1),
            }
        )
    return transactions


def _detect_house_report_type(text: str) -> str:
    """Classify a House PDF as PTR / Annual based on its header text."""
    upper = text.upper()
    if "PERIODIC TRANSACTION REPORT" in upper or "PERIODIC TRANSACTION" in upper:
        return "PTR"
    if "ANNUAL REPORT" in upper or "ANNUAL DISCLOSURE" in upper:
        return "Annual"
    return "PTR"


def parse_house_pdf(path: Path, chamber: Optional[str] = None) -> Dict[str, Any]:
    """Parse a House (or Senate) PDF filing into the standardized schema.

    Digital PDFs are read with ``pdfplumber``; scanned/image-based PDFs are
    transparently routed through ``pdf2image`` + ``pytesseract`` OCR.
    """
    meta = _metadata_from_path(path)
    pages_text = _extract_pdf_text(path)
    page_one = pages_text[0] if pages_text else ""
    full_text = "\n".join(pages_text)

    chamber_label = chamber or CHAMBER_LABELS.get(_chamber_from_path(path), "House")

    filer_name = meta["filer_name"]
    name_match = re.search(
        r"Name\s*[:\-]\s*([A-Z][A-Za-z\.'\-]+(?:\s+[A-Z][A-Za-z\.'\-]+){0,4})",
        full_text,
    )
    if name_match:
        filer_name = name_match.group(1).strip()

    filing_date = _filing_date_from_text(full_text, meta["year"], meta["month_dir"])

    # ---------------------------------------------------------------------
    # Extension filter: skip table extraction for extension request forms.
    # ---------------------------------------------------------------------
    header_upper = page_one.upper()
    if any(marker in header_upper for marker in EXTENSION_MARKERS):
        return {
            "doc_id": meta["doc_id"],
            "chamber": chamber_label,
            "filer_name": filer_name,
            "filing_date": filing_date,
            "report_type": "Extension",
            "transactions": [],
        }

    report_type = _detect_house_report_type(page_one or full_text)

    transactions: List[Dict[str, str]] = []
    for table in _extract_pdf_tables(path):
        transactions.extend(_rows_to_transactions(table))

    if not transactions:
        transactions = _transactions_from_text(full_text)

    # De-duplicate identical rows while preserving order.
    seen = set()
    unique_transactions = []
    for tx in transactions:
        key = tuple(sorted(tx.items()))
        if key not in seen:
            seen.add(key)
            unique_transactions.append(tx)

    return {
        "doc_id": meta["doc_id"],
        "chamber": chamber_label,
        "filer_name": filer_name,
        "filing_date": filing_date,
        "report_type": report_type,
        "transactions": unique_transactions,
    }


# ==============================================================================
# DISPATCH, DISCOVERY & PERSISTENCE
# ==============================================================================

def parse_document(path: Path) -> Optional[Dict[str, Any]]:
    """Dispatch a single file to the correct parser based on its extension."""
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return parse_senate_html(path)
    if suffix == ".pdf":
        chamber = CHAMBER_LABELS.get(_chamber_from_path(path), "House")
        return parse_house_pdf(path, chamber=chamber)
    return None


def iter_documents(chamber: Optional[str] = None, doc_id: Optional[str] = None) -> List[Path]:
    """Discover raw disclosure documents on the mounted volume."""
    base = get_base_output_dir()

    if chamber and chamber.lower() in CHAMBER_DIRS:
        chambers = [chamber.lower()]
    else:
        chambers = list(CHAMBER_DIRS.keys())

    documents: List[Path] = []
    for key in chambers:
        chamber_dir = base / CHAMBER_DIRS[key]
        if not chamber_dir.exists():
            continue
        for path in chamber_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".pdf", ".html", ".htm"):
                continue
            if doc_id and path.stem != str(doc_id):
                continue
            documents.append(path)
    return documents


def save_parsed(document: Dict[str, Any]) -> Path:
    """Write a parsed document to ``{OUTPUT_BASE_DIR}/parsed_json/{doc_id}.json``."""
    output_dir = get_parsed_json_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{document['doc_id']}.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
    return output_path


def run_parse(
    chamber: Optional[str] = None,
    doc_id: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Parse every discovered document and persist the standardized JSON.

    Programmatic entrypoint used by both the CLI and the FastAPI microservice.
    """
    documents = iter_documents(chamber=chamber, doc_id=doc_id)
    output_dir = get_parsed_json_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    stats = {"PARSED": 0, "SKIPPED": 0, "FAILED": 0}

    print("=" * 70)
    print("   Congressional Disclosure Parsing & OCR Engine")
    print("=" * 70)
    print(f"Base directory  : {get_base_output_dir().resolve()}")
    print(f"Output directory: {output_dir.resolve()}")
    print(f"Chamber filter  : {chamber or 'all'}")
    print(f"Doc ID filter   : {doc_id or 'all'}")
    print(f"Force reparse   : {force}")
    print(f"Documents found : {len(documents)}")
    print("=" * 70)

    for path in documents:
        output_path = output_dir / f"{path.stem}.json"

        if not force and output_path.exists() and output_path.stat().st_size > 0:
            print(f"[SKIP] {path.name} (already parsed)")
            stats["SKIPPED"] += 1
            continue

        try:
            document = parse_document(path)
            if not document:
                print(f"[FAIL] {path.name} (unsupported format)")
                stats["FAILED"] += 1
                continue
            save_parsed(document)
            print(
                f"[OK] {path.name} -> {output_path.name} "
                f"({len(document['transactions'])} transactions)"
            )
            stats["PARSED"] += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[FAIL] {path.name}: {exc}")
            stats["FAILED"] += 1

    print("=" * 70)
    print("Finished Parsing:")
    print(f"  - Parsed  : {stats['PARSED']}")
    print(f"  - Skipped : {stats['SKIPPED']}")
    print(f"  - Failed  : {stats['FAILED']}")
    print("=" * 70)

    return {
        "status": "SUCCESS",
        "documents_found": len(documents),
        "stats": stats,
        "output_directory": str(output_dir.resolve()),
    }


if __name__ == "__main__":
    import sys

    chamber_arg = None
    doc_id_arg = None
    force_arg = False
    for arg in sys.argv[1:]:
        if arg.startswith("--chamber="):
            chamber_arg = arg.split("=", 1)[1]
        elif arg.startswith("--doc-id="):
            doc_id_arg = arg.split("=", 1)[1]
        elif arg in ("--force", "-f"):
            force_arg = True

    run_parse(chamber=chamber_arg, doc_id=doc_id_arg, force=force_arg)
