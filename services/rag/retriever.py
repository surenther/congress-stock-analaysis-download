"""
Scoped hybrid search engine for the RAG & Query Retrieval Microservice.

Responsibilities
----------------
* Generate a query embedding via the LiteLLM Proxy's OpenAI-compatible
  ``/v1/embeddings`` endpoint (authenticated with the service master key).
* Execute a parameterized SQL query against ``disclosure_embeddings`` that
  HARD-SCOPES results to the caller's ``allowed_chambers`` at the database level
  (``chamber = ANY($1::text[])``), so an unauthorized chamber can never be
  returned even if the application layer were bypassed.
* Provide a structured (no-LLM) search path that returns raw matching rows.

All optional filters are bound as positional parameters (``$n``) — never
string-interpolated — to prevent SQL injection.
"""

import logging
import os
from datetime import date as date_type
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("rag")

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Base URL of the LiteLLM Proxy container (internal Compose network).
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")

# Service master key used to authenticate to the LiteLLM Proxy.
# Fail fast on a missing/placeholder key: the old "sk-change-me" default would
# let any caller able to reach the proxy use the service's credentials.
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "").strip()
if not LITELLM_MASTER_KEY or LITELLM_MASTER_KEY in {"sk-change-me", "change-me"}:
    raise RuntimeError(
        "LITELLM_MASTER_KEY must be set to the LiteLLM Proxy master key. "
        "The insecure default 'sk-change-me' is not allowed."
    )

# Embedding model alias for query vectors. This is the SAME ``EMBEDDING_MODEL``
# used by the vectorizer to populate ``disclosure_embeddings``, so query and
# stored vectors always share a model (required for meaningful similarity).
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openrouter-embed")

# Per-request timeout (seconds) for the proxy embeddings call.
REQUEST_TIMEOUT = float(os.getenv("RAG_REQUEST_TIMEOUT", "120"))

# ==============================================================================
# HYBRID SEARCH SQL
# ==============================================================================
# The chamber pre-filter (``chamber = ANY($1::text[])``) is the database-level
# enforcement of CBAC. Optional filters are applied only when their parameter is
# non-NULL. Results are ordered by cosine distance (ascending = most similar).
#
# Parameter map:
#   $1  allowed_chambers  text[]
#   $2  ticker            text   (NULL = no filter)
#   $3  is_market_trade   bool   (NULL = no filter)
#   $4  start_date        date   (NULL = no filter)
#   $5  end_date          date   (NULL = no filter)
#   $6  query_vector      vector
#   $7  limit             int
# Asset-class selector -> SQL predicate on ``asset_category``. "Other" is every
# category that is not a plain Stock or Bond. "All" applies no predicate. The
# predicate is a fixed whitelist (never user input), so it is safe to interpolate.
_ASSET_CLASS_PREDICATES = {
    "Stock": "asset_category = 'Stock'",
    "Bond": "asset_category = 'Bond'",
    "Other": "(asset_category IS NULL OR asset_category NOT IN ('Stock', 'Bond'))",
}


def _asset_class_predicate(asset_class: Optional[str]) -> str:
    """Return an AND-able SQL predicate for the asset class (or '' for All)."""
    predicate = _ASSET_CLASS_PREDICATES.get(asset_class or "All", "")
    return f"AND {predicate}" if predicate else ""


_SEARCH_SQL = """
SELECT
    doc_id, chamber, filer_name, filing_date, report_type,
    contains_market_trades, is_market_trade, ticker, asset_name,
    asset_category, action, date, value_range, ownership, comment, chunk_text,
    (1 - (embedding <=> $8::vector)) AS similarity_score
FROM disclosure_embeddings
WHERE
    chamber = ANY($1::text[])
    AND ($2::text IS NULL OR ticker = $2)
    AND ($3::boolean IS NULL OR is_market_trade = $3)
    AND ($4::date IS NULL OR date >= $4::date)
    AND ($5::date IS NULL OR date <= $5::date)
    AND ($6::text IS NULL OR filer_name ILIKE $6)
    AND ($7::text IS NULL OR action ILIKE $7)
    {asset_predicate}
ORDER BY embedding <=> $8::vector ASC
LIMIT $9;
"""

# Structured search: same chamber scoping and optional filters, but no vector
# ordering and no embedding generation. Returns raw rows.
#
# Parameter map:
#   $1  allowed_chambers  text[]
#   $2  ticker            text   (NULL = no filter)
#   $3  is_market_trade   bool   (NULL = no filter)
#   $4  start_date        date   (NULL = no filter)
#   $5  end_date          date   (NULL = no filter)
#   $6  asset_category    text   (NULL = no filter, exact case-insensitive)
#   $7  filer_name        text   (NULL = no filter, substring case-insensitive)
#   $8  action            text   (NULL = no filter, substring case-insensitive)
#   $9  is_late           bool   (NULL = no filter; true = filed >45 days after trade)
#   $10 asset_name        text   (NULL = no filter, substring case-insensitive)
#   $11 limit             int
#   $12 offset            int
_STRUCTURED_SQL = """
SELECT
    doc_id, chamber, filer_name, filing_date, report_type,
    contains_market_trades, is_market_trade, ticker, asset_name,
    asset_category, action, date, value_range, ownership, comment, chunk_text
FROM disclosure_embeddings
WHERE
    chamber = ANY($1::text[])
    AND ($2::text IS NULL OR ticker = $2)
    AND ($3::boolean IS NULL OR is_market_trade = $3)
    AND ($4::date IS NULL OR date >= $4::date)
    AND ($5::date IS NULL OR date <= $5::date)
    AND ($6::text IS NULL OR asset_category ILIKE $6)
    AND ($7::text IS NULL OR filer_name ILIKE $7)
    AND ($8::text IS NULL OR action ILIKE $8)
    AND ($9::boolean IS NULL OR (filing_date - date) > 45)
    AND ($10::text IS NULL OR asset_name ILIKE $10)
ORDER BY filing_date DESC NULLS LAST, doc_id ASC
LIMIT $11 OFFSET $12;
"""

# Count of rows matching the same structured filters (for accurate pagination).
_STRUCTURED_COUNT_SQL = """
SELECT COUNT(*)
FROM disclosure_embeddings
WHERE
    chamber = ANY($1::text[])
    AND ($2::text IS NULL OR ticker = $2)
    AND ($3::boolean IS NULL OR is_market_trade = $3)
    AND ($4::date IS NULL OR date >= $4::date)
    AND ($5::date IS NULL OR date <= $5::date)
    AND ($6::text IS NULL OR asset_category ILIKE $6)
    AND ($7::text IS NULL OR filer_name ILIKE $7)
    AND ($8::text IS NULL OR action ILIKE $8)
    AND ($9::boolean IS NULL OR (filing_date - date) > 45)
    AND ($10::text IS NULL OR asset_name ILIKE $10)
"""


# ==============================================================================
# EMBEDDINGS CLIENT
# ==============================================================================

def _extract_cost(response: "httpx.Response", data: Any) -> float:
    """Extract the LiteLLM-reported request cost (USD) from a proxy response."""
    raw = response.headers.get("x-litellm-response-cost")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    if isinstance(data, dict):
        for key in ("response_cost", "cost"):
            value = data.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
    return 0.0


def embed_query(text: str, model: Optional[str] = None) -> Dict[str, Any]:
    """Generate a single query embedding via the LiteLLM Proxy.

    Returns a dict with ``vector`` (list of floats), ``cost`` (USD as reported by
    the proxy, ``0.0`` if unavailable), and ``usage`` (token usage dict, may be
    empty). Raises ``RuntimeError`` on a proxy error or an unexpected shape.
    """
    resolved_model = model or DEFAULT_EMBEDDING_MODEL
    base = LITELLM_PROXY_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": resolved_model, "input": [text]}

    logger.debug("POST %s/v1/embeddings model=%s", base, resolved_model)
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(f"{base}/v1/embeddings", headers=headers, json=payload)
        if response.status_code == 404:
            logger.debug("Falling back to %s/embeddings", base)
            response = client.post(f"{base}/embeddings", headers=headers, json=payload)
        if response.status_code >= 400:
            logger.error(
                "LiteLLM embeddings error HTTP %s for model %s: %s",
                response.status_code, resolved_model, response.text[:500],
            )
            raise RuntimeError(
                f"LiteLLM Proxy returned HTTP {response.status_code} for embeddings "
                f"model '{resolved_model}': {response.text[:1000]}"
            )
        data = response.json()
        cost = _extract_cost(response, data)
        usage = data.get("usage") if isinstance(data, dict) else None

    try:
        entries = sorted(data["data"], key=lambda entry: entry.get("index", 0))
        vector = entries[0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected LiteLLM embeddings response shape: {data}"
        ) from exc
    return {"vector": vector, "cost": cost, "usage": usage or {}}


# ==============================================================================
# SEARCH HELPERS
# ==============================================================================

def _to_date(value: Optional[str]) -> Optional[date_type]:
    """Coerce an ISO ``YYYY-MM-DD`` string to a ``date`` (or ``None``)."""
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert an asyncpg Record to a JSON-serializable dict."""
    result: Dict[str, Any] = {}
    for key in row.keys():
        value = row[key]
        if isinstance(value, date_type):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


async def hybrid_search(
    pool,
    query: str,
    allowed_chambers: List[str],
    top_k: int = 10,
    ticker: Optional[str] = None,
    is_market_trade: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset_class: Optional[str] = None,
    filer_name: Optional[str] = None,
    action: Optional[str] = None,
    embedding_model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run a chamber-scoped hybrid (vector + metadata) search.

    ``allowed_chambers`` is enforced at the SQL level via ``chamber = ANY(...)``.
    ``asset_class`` (Stock/Bond/Other/All), ``filer_name`` and ``action`` are
    optional metadata filters used for scoped chat execution. Returns a list of
    row dicts including ``similarity_score``.
    """
    embedding = embed_query(query, model=embedding_model)
    filer_like = f"%{filer_name}%" if filer_name else None
    action_like = f"%{action}%" if action else None
    sql = _SEARCH_SQL.format(asset_predicate=_asset_class_predicate(asset_class))
    params = (
        list(allowed_chambers),
        ticker,
        is_market_trade,
        _to_date(start_date),
        _to_date(end_date),
        filer_like,
        action_like,
        embedding["vector"],
        top_k,
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)
    return {
        "results": [_row_to_dict(row) for row in rows],
        "embedding_cost": embedding["cost"],
        "embedding_usage": embedding["usage"],
    }


async def structured_search(
    pool,
    allowed_chambers: List[str],
    top_k: int = 50,
    offset: int = 0,
    ticker: Optional[str] = None,
    is_market_trade: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset_category: Optional[str] = None,
    filer_name: Optional[str] = None,
    action: Optional[str] = None,
    is_late: Optional[bool] = None,
    asset_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a chamber-scoped structured search WITHOUT embedding or LLM calls.

    ``allowed_chambers`` is enforced at the SQL level via ``chamber = ANY(...)``.
    Returns a dict with ``results`` (the requested page of rows, newest first)
    and ``total`` (the full count of matching rows, for accurate pagination).

    ``filer_name``, ``action`` and ``asset_name`` are matched as case-insensitive
    substrings; ``asset_category`` is an exact case-insensitive match. ``is_late``
    (when true) restricts to filings made more than 45 days after the trade date.
    """
    filer_like = f"%{filer_name}%" if filer_name else None
    action_like = f"%{action}%" if action else None
    asset_name_like = f"%{asset_name}%" if asset_name else None
    filter_params = (
        list(allowed_chambers),
        ticker,
        is_market_trade,
        _to_date(start_date),
        _to_date(end_date),
        asset_category,
        filer_like,
        action_like,
        is_late,
        asset_name_like,
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(_STRUCTURED_SQL, *filter_params, top_k, offset)
        total = await conn.fetchval(_STRUCTURED_COUNT_SQL, *filter_params)
    return {
        "results": [_row_to_dict(row) for row in rows],
        "total": int(total or 0),
    }
