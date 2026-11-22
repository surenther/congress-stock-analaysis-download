#!/usr/bin/env python3
"""
Embedding generation + pgvector persistence for the Vectorizer Microservice.

Text chunks are sent in batches to the LiteLLM Proxy's OpenAI-compatible
embeddings endpoint (``/v1/embeddings``), authenticated with the service master
key. The returned float vectors are upserted into ``disclosure_embeddings``
alongside their relational metadata.

Smart deduplication lives here too: :func:`vectorize_document` skips a document
whose rows already exist unless ``force`` is set, in which case the existing rows
are deleted and regenerated.
"""

import asyncio
import logging
import os
from datetime import date as date_type
from typing import Any, Dict, List, Optional, Tuple

import httpx

import chunker

logger = logging.getLogger("vectorizer")

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Base URL of the LiteLLM Proxy container (internal Compose network).
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")

# Service master key used to authenticate to the LiteLLM Proxy.
# Fail fast on a missing/placeholder key: a well-known default would let any
# caller able to reach the proxy use the service's credentials.
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "").strip()
if not LITELLM_MASTER_KEY or LITELLM_MASTER_KEY in {"sk-change-me", "change-me"}:
    raise RuntimeError(
        "LITELLM_MASTER_KEY must be set to the LiteLLM Proxy master key. "
        "The insecure default 'sk-change-me' is not allowed."
    )

# Default embedding model alias when the caller does not specify one. OpenRouter
# is the platform default (consistent with the parser's chat model), so no extra
# provider key is required beyond OPENROUTER_API_KEY.
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "openrouter-embed")

# Expected embedding dimension (must match the ``vector(N)`` column definition).
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

# Per-request timeout (seconds) for the proxy embeddings call.
REQUEST_TIMEOUT = float(os.getenv("EMBEDDING_REQUEST_TIMEOUT", "120"))

# Number of chunks sent per embeddings request.
BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))

# ==============================================================================
# UPSERT SQL
# ==============================================================================

_UPSERT_SQL = """
INSERT INTO disclosure_embeddings (
    doc_id, item_index, chamber, filer_name, filing_date, report_type,
    contains_market_trades, is_market_trade, ticker, asset_name,
    asset_category, action, date, value_range, ownership, comment,
    chunk_text, embedding
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
)
ON CONFLICT (doc_id, item_index) DO UPDATE SET
    chamber = EXCLUDED.chamber,
    filer_name = EXCLUDED.filer_name,
    filing_date = EXCLUDED.filing_date,
    report_type = EXCLUDED.report_type,
    contains_market_trades = EXCLUDED.contains_market_trades,
    is_market_trade = EXCLUDED.is_market_trade,
    ticker = EXCLUDED.ticker,
    asset_name = EXCLUDED.asset_name,
    asset_category = EXCLUDED.asset_category,
    action = EXCLUDED.action,
    date = EXCLUDED.date,
    value_range = EXCLUDED.value_range,
    ownership = EXCLUDED.ownership,
    comment = EXCLUDED.comment,
    chunk_text = EXCLUDED.chunk_text,
    embedding = EXCLUDED.embedding
"""


# ==============================================================================
# LITELLM EMBEDDINGS CLIENT
# ==============================================================================

def _extract_cost(response: "httpx.Response", data: Any) -> float:
    """Extract the LiteLLM-reported request cost (USD) from a proxy response.

    LiteLLM returns the cost in the ``x-litellm-response-cost`` response header.
    As a fallback, a ``response_cost`` / ``cost`` field in the JSON body is used.
    Returns ``0.0`` when no cost information is available.
    """
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


def embed_texts(texts: List[str], model: str) -> Tuple[List[List[float]], float]:
    """Send a batch of text chunks to the LiteLLM Proxy.

    Returns a ``(vectors, cost)`` tuple, where ``cost`` is the request cost in
    USD as reported by the proxy (``0.0`` if unavailable).

    The service master key is attached as a Bearer token. The proxy's
    OpenAI-compatible ``/v1/embeddings`` endpoint is used, falling back to
    ``/embeddings`` if the former returns HTTP 404.
    """
    if not texts:
        return [], 0.0

    base = LITELLM_PROXY_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}

    logger.debug(
        "POST %s/v1/embeddings model=%s batch=%d", base, model, len(texts)
    )
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(f"{base}/v1/embeddings", headers=headers, json=payload)
        if response.status_code == 404:
            logger.debug("Falling back to %s/embeddings", base)
            response = client.post(f"{base}/embeddings", headers=headers, json=payload)
        if response.status_code >= 400:
            logger.error(
                "LiteLLM embeddings error HTTP %s for model %s: %s",
                response.status_code, model, response.text[:500],
            )
            raise RuntimeError(
                f"LiteLLM Proxy returned HTTP {response.status_code} for embeddings "
                f"model '{model}': {response.text[:1000]}"
            )
        data = response.json()
        cost = _extract_cost(response, data)

    try:
        entries = sorted(data["data"], key=lambda entry: entry.get("index", 0))
        vectors = [entry["embedding"] for entry in entries]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Unexpected LiteLLM embeddings response shape: {data}") from exc

    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Embedding count mismatch: requested {len(texts)}, received {len(vectors)}"
        )
    return vectors, cost


# ==============================================================================
# PERSISTENCE HELPERS
# ==============================================================================

def _to_date(value: Optional[str]) -> Optional[date_type]:
    """Coerce an ISO ``YYYY-MM-DD`` string to a ``date`` (or ``None``)."""
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _row_from_chunk(chunk: Dict[str, Any], vector: List[float]) -> tuple:
    """Build the positional parameter tuple for the upsert statement."""
    return (
        chunk["doc_id"],
        chunk["item_index"],
        chunk["chamber"],
        chunk["filer_name"],
        _to_date(chunk["filing_date"]),
        chunk["report_type"],
        chunk["contains_market_trades"],
        chunk["is_market_trade"],
        chunk["ticker"],
        chunk["asset_name"],
        chunk["asset_category"],
        chunk["action"],
        _to_date(chunk["date"]),
        chunk["value_range"],
        chunk["ownership"],
        chunk["comment"],
        chunk["chunk_text"],
        vector,
    )


async def _upsert_rows(pool, rows: List[tuple]) -> None:
    """Upsert embedding rows using ``ON CONFLICT (doc_id, item_index)``."""
    if not rows:
        return
    async with pool.acquire() as conn:
        await conn.executemany(_UPSERT_SQL, rows)


async def is_already_vectorized(pool, doc_id: str) -> bool:
    """Return True if any embedding rows already exist for ``doc_id``."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM disclosure_embeddings WHERE doc_id = $1)",
            doc_id,
        )


async def get_vectorized_doc_ids(pool) -> set:
    """Return the set of ``doc_id`` values that already have embedding rows.

    Used by the bulk trigger to select unprocessed documents in a single query
    instead of issuing one ``EXISTS`` check per parsed JSON file.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT doc_id FROM disclosure_embeddings"
        )
    return {row["doc_id"] for row in rows}


# ==============================================================================
# ORCHESTRATION
# ==============================================================================

async def vectorize_document(
    pool,
    doc_id: str,
    model: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Vectorize a single parsed document end-to-end.

    Returns a result dict with a ``status`` of ``VECTORIZED``,
    ``SKIPPED_ALREADY_VECTORIZED``, or ``NO_ITEMS`` plus the item count.

    Deduplication: if rows for ``doc_id`` already exist and ``force`` is false,
    embedding generation is skipped. If ``force`` is true, the existing rows are
    deleted and regenerated.
    """
    resolved_model = model or DEFAULT_EMBEDDING_MODEL

    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM disclosure_embeddings WHERE doc_id = $1", doc_id
        )

    if existing and not force:
        logger.info(
            "SKIPPED_ALREADY_VECTORIZED doc_id=%s rows=%d", doc_id, existing
        )
        return {
            "status": "SKIPPED_ALREADY_VECTORIZED",
            "doc_id": doc_id,
            "items": int(existing),
            "cost": 0.0,
        }

    if existing and force:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM disclosure_embeddings WHERE doc_id = $1", doc_id
            )
        logger.info(
            "force=true: deleted %d existing rows for doc_id=%s", existing, doc_id
        )

    document = await asyncio.to_thread(chunker.load_parsed_document, doc_id)
    chunks = chunker.build_chunks(document)
    if not chunks:
        logger.info("No disclosure items to vectorize for doc_id=%s", doc_id)
        return {"status": "NO_ITEMS", "doc_id": doc_id, "items": 0, "cost": 0.0}

    vectors: List[List[float]] = []
    total_cost = 0.0
    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        batch_vectors, batch_cost = await asyncio.to_thread(
            embed_texts, [c["chunk_text"] for c in batch], resolved_model
        )
        vectors.extend(batch_vectors)
        total_cost += batch_cost

    rows = [_row_from_chunk(chunk, vector) for chunk, vector in zip(chunks, vectors)]
    await _upsert_rows(pool, rows)
    logger.info(
        "VECTORIZED doc_id=%s model=%s items=%d cost=$%.6f",
        doc_id, resolved_model, len(rows), total_cost,
    )
    return {
        "status": "VECTORIZED",
        "doc_id": doc_id,
        "items": len(rows),
        "cost": total_cost,
    }
