#!/usr/bin/env python3
"""
LLM-powered Congressional Disclosure Extraction Engine.

This module replaces the previous hand-written regex/OCR scrapers. It reads the
raw text of a disclosure document from the mounted ``/data`` volume, sends that
text through a **LiteLLM Proxy** (which routes to OpenRouter, Hugging Face, or a
local Ollama/vLLM backend), and writes a standardized, structured JSON document
to ``/data/parsed_json/{doc_id}.json``.

The engine is intentionally thin: all of the domain intelligence (trade vs.
income classification, extension-form handling, date normalization, and the
anti-hallucination rules) lives in the system prompt below, so the extraction
behaviour can be tuned without touching Python code.

Standardized output schema::

    {
      "doc_id": "10073198",
      "chamber": "House",
      "filer_name": "Laurie Buckhout",
      "filing_date": "2026-01-24",
      "report_type": "PTR",
      "contains_market_trades": true,
      "items": [
        {
          "is_market_trade": true,
          "ticker": "NVDA",
          "asset_name": "NVIDIA Corporation",
          "asset_category": "Stock",
          "action": "Purchase",
          "date": "2026-01-15",
          "value_range": "$15,001 - $50,000",
          "ownership": "Self",
          "comment": null
        }
      ]
    }
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Destination subfolder (relative to OUTPUT_BASE_DIR) for the parsed JSON files.
PARSED_JSON_DIRNAME = "parsed_json"

# Base URL of the LiteLLM Proxy container (internal Compose network).
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")

# Service master key used to authenticate to the LiteLLM Proxy.
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-change-me")

# Default LiteLLM model alias when the caller does not specify one.
DEFAULT_MODEL = os.getenv("LITELLM_DEFAULT_MODEL", "openrouter-deepseek-flash")

# Per-request timeout (seconds) for the proxy call.
REQUEST_TIMEOUT = float(os.getenv("LITELLM_REQUEST_TIMEOUT", "180"))

# Whether to request provider-native JSON mode (``response_format=json_object``).
# Disabled by default for maximum provider compatibility; the engine always
# parses and validates JSON defensively regardless. Enable with
# LITELLM_USE_JSON_MODE=true if your provider supports it.
USE_JSON_MODE = os.getenv("LITELLM_USE_JSON_MODE", "false").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Hard cap on the number of characters of document text sent to the model, to
# keep requests within provider context windows and control cost.
MAX_INPUT_CHARS = int(os.getenv("PARSER_MAX_INPUT_CHARS", "120000"))

# Allowed enum values (kept in sync with the system prompt and the README).
REPORT_TYPES = ["PTR", "Annual", "Candidate", "Termination", "Extension"]
ASSET_CATEGORIES = [
    "Stock",
    "Option",
    "Bond",
    "Crypto",
    "Mutual Fund/ETF",
    "Earned Income/Salary",
    "Bank Deposit",
    "Real Estate",
    "Other",
]
ACTIONS = [
    "Purchase",
    "Sale",
    "Partial Sale",
    "Exchange",
    "Received Income",
    "Holding Only",
]
OWNERSHIPS = ["Self", "Spouse", "Joint", "Dependent"]

# Maps a logical chamber name to the on-disk subfolder written by the downloader.
CHAMBER_DIRS = {"house": "house_rep", "senate": "senate"}

# Human-readable chamber label stored in the parsed JSON.
CHAMBER_LABELS = {"house": "House", "senate": "Senate"}

# File extensions the engine knows how to read.
SUPPORTED_SUFFIXES = (".pdf", ".html", ".htm", ".txt", ".text")


def get_base_output_dir() -> Path:
    """Return the root storage directory (the mounted host volume)."""
    base = os.getenv("OUTPUT_BASE_DIR", "/data")
    return Path(base) if base else Path("/data")


def get_parsed_json_dir() -> Path:
    """Return the directory where parsed JSON documents are written."""
    return get_base_output_dir() / PARSED_JSON_DIRNAME


def is_already_parsed(doc_id: str) -> bool:
    """Return True if a non-empty parsed JSON already exists for ``doc_id``.

    This is the parser's equivalent of the downloader's skip-if-present check:
    a document that has already produced ``parsed_json/{doc_id}.json`` is not
    re-processed (unless the caller explicitly sets ``force=true``).
    """
    output_path = get_parsed_json_dir() / f"{doc_id}.json"
    return output_path.exists() and output_path.stat().st_size > 0


def chamber_label_from_path(file_path: str) -> str:
    """Infer the human-readable chamber label from a document path.

    Falls back to ``"House"`` when the path does not contain a known chamber
    folder (``house_rep`` or ``senate``).
    """
    parts = Path(file_path).parts
    for key, dirname in CHAMBER_DIRS.items():
        if dirname in parts:
            return CHAMBER_LABELS[key]
    return "House"


def iter_documents(chamber: Optional[str] = None) -> List[Dict[str, str]]:
    """Discover raw disclosure documents on the mounted volume.

    Walks ``{OUTPUT_BASE_DIR}/{house_rep,senate}/...`` and returns one descriptor
    per supported file. ``chamber`` may be ``"house"``, ``"senate"``, ``"all"``,
    or ``None`` (all chambers).
    """
    base = get_base_output_dir()

    if chamber and chamber.lower() in CHAMBER_DIRS:
        keys = [chamber.lower()]
    else:
        keys = list(CHAMBER_DIRS.keys())

    documents: List[Dict[str, str]] = []
    for key in keys:
        chamber_dir = base / CHAMBER_DIRS[key]
        if not chamber_dir.exists():
            continue
        for path in sorted(chamber_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                relative = str(path.relative_to(base))
            except ValueError:
                relative = str(path)
            documents.append(
                {
                    "doc_id": path.stem,
                    "chamber": CHAMBER_LABELS[key],
                    "file_path": relative,
                }
            )
    return documents


# ==============================================================================
# SYSTEM PROMPT & EXTRACTION GUIDELINES
# ==============================================================================

SYSTEM_PROMPT = """You are a meticulous financial-disclosure extraction engine for \
U.S. Congressional filings (House and Senate). You convert the raw text of a \
single disclosure document into a strict, structured JSON object.

You MUST return ONLY a single valid JSON object. Do not wrap it in markdown, do \
not add commentary, and do not include any text before or after the JSON.

=====================================================================
OUTPUT JSON SCHEMA
=====================================================================
{
  "doc_id": "<string: the document id supplied by the caller>",
  "chamber": "<string: 'House' or 'Senate'>",
  "filer_name": "<string: the filing member's name, or null>",
  "filing_date": "<string: YYYY-MM-DD, or null>",
  "report_type": "<one of: PTR, Annual, Candidate, Termination, Extension>",
  "contains_market_trades": <boolean>,
  "items": [
    {
      "is_market_trade": <boolean>,
      "ticker": "<string ticker symbol, or null>",
      "asset_name": "<string: asset/company name, income source, or employer>",
      "asset_category": "<one of: Stock, Option, Bond, Crypto, Mutual Fund/ETF, \
Earned Income/Salary, Bank Deposit, Real Estate, Other>",
      "action": "<one of: Purchase, Sale, Partial Sale, Exchange, Received Income, \
Holding Only>",
      "date": "<string: YYYY-MM-DD, or null>",
      "value_range": "<string: the disclosed dollar range, or null>",
      "ownership": "<one of: Self, Spouse, Joint, Dependent>",
      "comment": "<string: optional context, or null>"
    }
  ]
}

=====================================================================
DUAL-CATEGORY CLASSIFICATION (TRADES vs. NON-TRADE DISCLOSURES)
=====================================================================
Disclosures contain BOTH:
  (a) Stock trading reports (Periodic Transaction Reports / PTRs) that list
      active market trades in stocks, options, bonds, mutual funds/ETFs, and
      crypto; AND
  (b) Non-trade disclosures (typically Annual reports) that list salary, a
      spouse's earned income, consulting fees, honoraria, bank accounts, blind
      trust holdings, or real estate.

You MUST strictly isolate active market trades from non-trade items:
  * Set "is_market_trade": true ONLY for active public-market assets
    (stocks, options, bonds, crypto, mutual funds/ETFs).
  * Set "is_market_trade": false for salary, spouse income, consulting fees,
    honoraria, bank deposits, real estate, and any other non-trade item.
  * Set the document-level "contains_market_trades" to true if ANY item is a
    market trade, otherwise false.

=====================================================================
TICKER RULES (CRITICAL — NO HALLUCINATION)
=====================================================================
  * Populate "ticker" ONLY for active public-market assets whose symbol is
    explicitly present in the document text.
  * "ticker" MUST be null for salary, earned income, bank deposits, real
    estate, and any non-public or privately held asset.
  * NEVER invent, guess, or infer a ticker symbol. If the symbol is not
    literally in the text, use null.

=====================================================================
ASSET CATEGORY RULES
=====================================================================
Choose exactly one "asset_category" per item:
  * Stock, Option, Bond, Crypto, Mutual Fund/ETF  -> market assets.
  * Earned Income/Salary  -> salary, wages, consulting fees, honoraria.
  * Bank Deposit          -> checking/savings accounts, CDs, money markets.
  * Real Estate           -> property, land, rental real estate.
  * Other                 -> anything that does not fit the above.

=====================================================================
ACTION / TRANSACTION TYPE RULES
=====================================================================
Choose exactly one "action" per item:
  * Purchase, Sale, Partial Sale, Exchange  -> for market trades.
  * Received Income                         -> for salary/income items.
  * Holding Only                            -> for assets merely held (e.g. an
    annual report listing a holding with no transaction).

=====================================================================
EXTENSION FORM HANDLING
=====================================================================
If Page 1 of the document contains extension-request text (for example
"EXTENSION REQUEST FORM", "Request for Extension", or similar language), you
MUST:
  * Set "report_type": "Extension".
  * Set "contains_market_trades": false.
  * Return an EMPTY "items" array (skip all item extraction).

=====================================================================
DATE NORMALIZATION
=====================================================================
  * Convert every extracted transaction or disclosure date into strict
    YYYY-MM-DD format (e.g. "1/15/2026" -> "2026-01-15").
  * If a date is missing or cannot be determined, use null. Never guess.

=====================================================================
FACTUALITY (STRICT)
=====================================================================
  * Extract ONLY items that are explicitly present in the input text.
  * Do NOT hallucinate, infer, complete, or fabricate any field, item, ticker,
    amount, or date.
  * If the document contains no extractable items, return an empty "items"
    array.
  * Preserve the disclosed dollar range verbatim in "value_range" (e.g.
    "$15,001 - $50,000").

Return the JSON object now."""


# ==============================================================================
# DOCUMENT TEXT EXTRACTION (raw content only — no domain parsing)
# ==============================================================================

def _read_pdf_text(path: Path) -> str:
    """Extract the raw text layer from a PDF using pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages)


def _read_html_text(path: Path) -> str:
    """Extract the visible text from a Senate HTML filing."""
    from bs4 import BeautifulSoup

    html = path.read_text(encoding="utf-8", errors="ignore")
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def read_document_text(path: Path) -> str:
    """Read the raw text content of a supported disclosure document.

    Supported formats: ``.pdf`` (House filings), ``.html``/``.htm`` (Senate
    filings), and ``.txt``/``.text`` (pre-extracted text).
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf_text(path)
    if suffix in (".html", ".htm"):
        return _read_html_text(path)
    if suffix in (".txt", ".text"):
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported document format: {suffix or '(none)'}")


# ==============================================================================
# LITELLM PROXY CLIENT
# ==============================================================================

def call_litellm_proxy(
    text: str,
    model: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Send document text through the LiteLLM Proxy and return the parsed JSON.

    The service master key is attached for authentication, and caller metadata
    (user, roles, doc_id, ...) is forwarded so the proxy can emit audit logs.

    Provider-native JSON mode (``response_format``) is only sent when
    ``LITELLM_USE_JSON_MODE`` is enabled, and is automatically dropped and
    retried once if a provider rejects it with HTTP 400. On any other error the
    proxy's response body is surfaced so the failure is diagnosable.
    """
    url = f"{LITELLM_PROXY_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
    }

    truncated = text[:MAX_INPUT_CHARS]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": truncated},
        ],
        "temperature": 0,
    }
    if USE_JSON_MODE:
        payload["response_format"] = {"type": "json_object"}
    # Forward caller metadata for LiteLLM audit logging (best-effort).
    if metadata:
        payload["metadata"] = metadata

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(url, headers=headers, json=payload)

        # Some providers reject `response_format`; retry once without it.
        if response.status_code == 400 and "response_format" in payload:
            payload.pop("response_format", None)
            response = client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(
                f"LiteLLM Proxy returned HTTP {response.status_code} for model "
                f"'{model}': {response.text[:1000]}"
            )
        data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LiteLLM response shape: {data}") from exc

    return _parse_json_content(content)


def _parse_json_content(content: Any) -> Dict[str, Any]:
    """Parse the model's message content into a dict, tolerating code fences."""
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise RuntimeError(f"Model returned non-text content: {content!r}")

    cleaned = content.strip()
    if cleaned.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing fence.
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[: -len("```")]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model did not return valid JSON: {content!r}") from exc


# ==============================================================================
# NORMALIZATION
# ==============================================================================

def _normalize_date(value: Any) -> Optional[str]:
    """Coerce a date value to strict ``YYYY-MM-DD`` or ``None``."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%Y/%m/%d",
                "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_enum(value: Any, allowed: List[str], default: str) -> str:
    """Match a value case-insensitively against an allowed enum list."""
    if isinstance(value, str):
        for candidate in allowed:
            if value.strip().lower() == candidate.lower():
                return candidate
    return default


def _normalize_item(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single extracted item into the canonical schema."""
    is_trade = bool(raw.get("is_market_trade", False))

    ticker = raw.get("ticker")
    if isinstance(ticker, str):
        ticker = ticker.strip().upper() or None
    else:
        ticker = None
    # Enforce the ticker rule: non-trade items never carry a ticker.
    if not is_trade:
        ticker = None

    asset_name = raw.get("asset_name")
    asset_name = asset_name.strip() if isinstance(asset_name, str) else None

    comment = raw.get("comment")
    comment = comment.strip() if isinstance(comment, str) and comment.strip() else None

    value_range = raw.get("value_range")
    value_range = value_range.strip() if isinstance(value_range, str) else None

    return {
        "is_market_trade": is_trade,
        "ticker": ticker,
        "asset_name": asset_name,
        "asset_category": _normalize_enum(raw.get("asset_category"), ASSET_CATEGORIES, "Other"),
        "action": _normalize_enum(raw.get("action"), ACTIONS, "Holding Only"),
        "date": _normalize_date(raw.get("date")),
        "value_range": value_range,
        "ownership": _normalize_enum(raw.get("ownership"), OWNERSHIPS, "Self"),
        "comment": comment,
    }


def normalize_document(
    raw: Dict[str, Any],
    doc_id: str,
    chamber: str,
) -> Dict[str, Any]:
    """Normalize the model output into the canonical document schema."""
    report_type = _normalize_enum(raw.get("report_type"), REPORT_TYPES, "PTR")

    raw_items = raw.get("items")
    items: List[Dict[str, Any]] = []
    if isinstance(raw_items, list):
        for entry in raw_items:
            if isinstance(entry, dict):
                items.append(_normalize_item(entry))

    # Extension forms never contain items or market trades.
    if report_type == "Extension":
        items = []

    contains_market_trades = any(item["is_market_trade"] for item in items)

    filer_name = raw.get("filer_name")
    filer_name = filer_name.strip() if isinstance(filer_name, str) and filer_name.strip() else None

    return {
        "doc_id": doc_id,
        "chamber": chamber,
        "filer_name": filer_name,
        "filing_date": _normalize_date(raw.get("filing_date")),
        "report_type": report_type,
        "contains_market_trades": contains_market_trades,
        "items": items,
    }


# ==============================================================================
# ORCHESTRATION & PERSISTENCE
# ==============================================================================

def save_parsed(document: Dict[str, Any]) -> Path:
    """Write a parsed document to ``{OUTPUT_BASE_DIR}/parsed_json/{doc_id}.json``."""
    output_dir = get_parsed_json_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{document['doc_id']}.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
    return output_path


def extract_document(
    doc_id: str,
    chamber: str,
    file_path: str,
    model: Optional[str] = None,
    user_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract a single disclosure document end-to-end and persist the JSON.

    ``file_path`` is a path relative to the mounted ``/data`` volume (or an
    absolute path inside the container). The raw text is sent through the
    LiteLLM Proxy, normalized, and written to ``parsed_json/{doc_id}.json``.
    """
    base = get_base_output_dir()
    path = Path(file_path)
    if not path.is_absolute():
        path = base / file_path

    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    text = read_document_text(path)
    if not text.strip():
        raise ValueError(f"No extractable text in document: {path}")

    metadata = {
        "doc_id": doc_id,
        "chamber": chamber,
        "source_file": str(path),
        "model": model or DEFAULT_MODEL,
    }
    if user_metadata:
        metadata.update(user_metadata)

    raw = call_litellm_proxy(text, model or DEFAULT_MODEL, metadata=metadata)
    document = normalize_document(raw, doc_id=doc_id, chamber=chamber)
    save_parsed(document)
    return document
