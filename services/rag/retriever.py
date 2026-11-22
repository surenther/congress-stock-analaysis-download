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
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-change-me")

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
_SEARCH_SQL = """
SELECT
    doc_id, chamber, filer_name, filing_date, report_type,
    contains_market_trades, is_market_trade, ticker, asset_name,
    asset_category, action, date, value_range, ownership, comment, chunk_text,
    (1 - (embedding <=> $6::vector)) AS similarity_score
FROM disclosure_embeddings
WHERE
    chamber = ANY($1::text[])
    AND ($2::text IS NULL OR ticker = $2)
    AND ($3::boolean IS NULL OR is_market_trade = $3)
    AND ($4::date IS NULL OR date >= $4::date)
    AND ($5::date IS NULL OR date <= $5::date)
ORDER BY embedding <=> $6::vector ASC
LIMIT $7;
"""

# Structured search: same chamber scoping and optional filters, but no vector
# ordering and no embedding generation. Returns raw rows.
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
ORDER BY filing_date DESC NULLS LAST, doc_id ASC
LIMIT $6;
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


def embed_query(text: str, model: Optional[str] = None) -> List[float]:
    """Generate a single query embedding via the LiteLLM Proxy.

    Returns the embedding vector as a list of floats. Raises ``RuntimeError`` on
    a proxy error or an unexpected response shape.
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

    try:
        entries = sorted(data["data"], key=lambda entry: entry.get("index", 0))
        vector = entries[0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected LiteLLM embeddings response shape: {data}"
        ) from exc
    return vector


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
    embedding_model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run a chamber-scoped hybrid (vector + metadata) search.

    ``allowed_chambers`` is enforced at the SQL level via ``chamber = ANY(...)``.
    Returns a list of row dicts including ``similarity_score``.
    """
    vector = embed_query(query, model=embedding_model)
    params = (
        list(allowed_chambers),
        ticker,
        is_market_trade,
        _to_date(start_date),
        _to_date(end_date),
        vector,
        top_k,
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SEARCH_SQL, *params)
    return [_row_to_dict(row) for row in rows]


async def structured_search(
    pool,
    allowed_chambers: List[str],
    top_k: int = 50,
    ticker: Optional[str] = None,
    is_market_trade: Optional[bool] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Run a chamber-scoped structured search WITHOUT embedding or LLM calls.

    ``allowed_chambers`` is enforced at the SQL level via ``chamber = ANY(...)``.
    Returns raw matching rows ordered by filing date (newest first).
    """
    params = (
        list(allowed_chambers),
        ticker,
        is_market_trade,
        _to_date(start_date),
        _to_date(end_date),
        top_k,
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(_STRUCTURED_SQL, *params)
    return [_row_to_dict(row) for row in rows]
