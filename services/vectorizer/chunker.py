#!/usr/bin/env python3
"""
Semantic chunking for the Vectorizer Microservice.

Reads the standardized JSON documents produced by the Parser Service
(``/data/parsed_json/{doc_id}.json``) and converts every disclosure item into a
rich, natural-language text block suitable for embedding.

Path containment is enforced: only files that resolve to a location *inside*
``/data/parsed_json`` are read. Absolute paths and ``..`` traversal are rejected.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vectorizer")

# Destination subfolder (relative to OUTPUT_BASE_DIR) written by the parser.
PARSED_JSON_DIRNAME = "parsed_json"

# Document ids are used directly in filenames, so they must not contain path
# separators or traversal sequences.
_DOC_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def get_base_output_dir() -> Path:
    """Return the root storage directory (the mounted host volume)."""
    base = os.getenv("OUTPUT_BASE_DIR", "/data")
    return Path(base) if base else Path("/data")


def get_parsed_json_dir() -> Path:
    """Return the directory where the parser writes standardized JSON."""
    return get_base_output_dir() / PARSED_JSON_DIRNAME


def is_valid_doc_id(doc_id: Any) -> bool:
    """Return True if ``doc_id`` is safe to use in a filename."""
    return bool(
        isinstance(doc_id, str)
        and _DOC_ID_RE.match(doc_id)
        and ".." not in doc_id
    )


def parsed_document_path(doc_id: str) -> Path:
    """Resolve ``doc_id`` to a path strictly inside ``/data/parsed_json``.

    Raises ``ValueError`` for an invalid doc id or any path that escapes the
    parsed-JSON directory (absolute paths, ``..`` traversal, or symlinks).
    """
    if not is_valid_doc_id(doc_id):
        raise ValueError(f"Invalid doc_id: {doc_id!r}")
    base = get_parsed_json_dir().resolve()
    resolved = (base / f"{doc_id}.json").resolve()
    if not resolved.is_relative_to(base):
        raise ValueError("Path escapes the parsed_json directory")
    return resolved


def parsed_document_exists(doc_id: str) -> bool:
    """Return True if a non-empty parsed JSON exists for ``doc_id``."""
    try:
        path = parsed_document_path(doc_id)
    except ValueError:
        return False
    return path.exists() and path.stat().st_size > 0


def load_parsed_document(doc_id: str) -> Dict[str, Any]:
    """Load and return the standardized parsed JSON for ``doc_id``."""
    path = parsed_document_path(doc_id)
    if not path.exists():
        raise FileNotFoundError(f"Parsed document not found: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _clean(value: Any) -> Optional[str]:
    """Return a stripped string, or ``None`` for empty/non-string values."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def build_chunk_text(document: Dict[str, Any], item: Dict[str, Any]) -> str:
    """Build the rich natural-language text block for a single disclosure item.

    Format::

        Filer: {filer_name} ({chamber}) | Report: {report_type} | Filing Date: \
{filing_date} | Item: {asset_name} | Ticker: {ticker or 'N/A'} | Category: \
{asset_category} | Action: {action} | Transaction Date: {date or 'N/A'} | \
Value Range: {value_range or 'N/A'} | Owner: {ownership or 'N/A'} | Context: \
{comment or 'None'}
    """
    filer = _clean(document.get("filer_name")) or "Unknown"
    chamber = _clean(document.get("chamber")) or "Unknown"
    report = _clean(document.get("report_type")) or "Unknown"
    filing_date = _clean(document.get("filing_date")) or "N/A"
    asset_name = _clean(item.get("asset_name")) or "Unknown"
    ticker = _clean(item.get("ticker")) or "N/A"
    category = _clean(item.get("asset_category")) or "N/A"
    action = _clean(item.get("action")) or "N/A"
    date = _clean(item.get("date")) or "N/A"
    value_range = _clean(item.get("value_range")) or "N/A"
    ownership = _clean(item.get("ownership")) or "N/A"
    comment = _clean(item.get("comment")) or "None"
    return (
        f"Filer: {filer} ({chamber}) | Report: {report} | Filing Date: {filing_date} | "
        f"Item: {asset_name} | Ticker: {ticker} | Category: {category} | "
        f"Action: {action} | Transaction Date: {date} | Value Range: {value_range} | "
        f"Owner: {ownership} | Context: {comment}"
    )


def build_chunks(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a parsed document into one chunk descriptor per disclosure item.

    Each descriptor carries the relational metadata columns plus the generated
    ``chunk_text`` ready for embedding.
    """
    doc_id = _clean(document.get("doc_id"))
    chamber = _clean(document.get("chamber")) or "Unknown"
    filer_name = _clean(document.get("filer_name"))
    filing_date = _clean(document.get("filing_date"))
    report_type = _clean(document.get("report_type"))
    contains_market_trades = bool(document.get("contains_market_trades", False))

    items = document.get("items") or []
    chunks: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        chunks.append(
            {
                "doc_id": doc_id,
                "item_index": index,
                "chamber": chamber,
                "filer_name": filer_name,
                "filing_date": filing_date,
                "report_type": report_type,
                "contains_market_trades": contains_market_trades,
                "is_market_trade": bool(item.get("is_market_trade", False)),
                "ticker": _clean(item.get("ticker")),
                "asset_name": _clean(item.get("asset_name")) or "Unknown",
                "asset_category": _clean(item.get("asset_category")),
                "action": _clean(item.get("action")),
                "date": _clean(item.get("date")),
                "value_range": _clean(item.get("value_range")),
                "ownership": _clean(item.get("ownership")),
                "comment": _clean(item.get("comment")),
                "chunk_text": build_chunk_text(document, item),
            }
        )
    return chunks


def iter_parsed_documents(chamber: Optional[str] = None) -> List[Dict[str, str]]:
    """Discover parsed JSON documents on the mounted volume.

    ``chamber`` may be ``"house"``, ``"senate"``, ``"all"``, or ``None`` (all
    chambers). The chamber is read from each document's ``chamber`` field.
    """
    base = get_parsed_json_dir()
    if not base.exists():
        return []

    wanted = (chamber or "all").lower()
    documents: List[Dict[str, str]] = []
    for path in sorted(base.glob("*.json")):
        if not path.is_file():
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable parsed JSON %s: %s", path, exc)
            continue
        doc_chamber = (_clean(data.get("chamber")) or "").lower()
        if wanted != "all" and doc_chamber != wanted:
            continue
        documents.append(
            {
                "doc_id": _clean(data.get("doc_id")) or path.stem,
                "chamber": _clean(data.get("chamber")) or "Unknown",
            }
        )
    return documents
