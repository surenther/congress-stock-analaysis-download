"""
RAG synthesis engine for the RAG & Query Retrieval Microservice.

Builds a system prompt that embeds the caller's ``allowed_chambers``, sends the
retrieved disclosure contexts plus the user's question to the LiteLLM Proxy's
OpenAI-compatible ``/v1/chat/completions`` endpoint, and returns the synthesized
Markdown answer together with a compact citation list.

The caller's ``user_id`` and ``allowed_chambers`` are forwarded as request
metadata so the LiteLLM Proxy can emit audit logs.
"""

import json
import logging
import os
from datetime import date as _date
from typing import Any, Dict, Iterator, List, Optional

import httpx

logger = logging.getLogger("rag")

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Base URL of the LiteLLM Proxy container (internal Compose network).
LITELLM_PROXY_URL = os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000")

# Service master key used to authenticate to the LiteLLM Proxy.
# Fail fast on a missing/placeholder key (see retriever.py): the old
# "sk-change-me" default is a well-known credential and must never ship.
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "").strip()
if not LITELLM_MASTER_KEY or LITELLM_MASTER_KEY in {"sk-change-me", "change-me"}:
    raise RuntimeError(
        "LITELLM_MASTER_KEY must be set to the LiteLLM Proxy master key. "
        "The insecure default 'sk-change-me' is not allowed."
    )

# Default chat model alias for synthesis.
DEFAULT_MODEL = os.getenv("RAG_DEFAULT_MODEL", "openrouter-deepseek-flash")

# Per-request timeout (seconds) for the proxy chat call.
REQUEST_TIMEOUT = float(os.getenv("RAG_REQUEST_TIMEOUT", "180"))

# Hard cap on the number of characters of retrieved context sent to the model.
MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "60000"))

# ==============================================================================
# SYSTEM PROMPT
# ==============================================================================

SYSTEM_PROMPT_TEMPLATE = (
    "You are a friendly congressional financial-disclosure analyst speaking to a "
    "non-technical user through a web dashboard. Answer the user's question using "
    "ONLY the provided disclosure contexts. You are operating under strict "
    "chamber permissions for: {allowed_chambers}.\n\n"
    "How to answer:\n"
    "- Explain findings in clear, plain, easy-to-understand language a general "
    "audience can follow. Lead with the key takeaway, then supporting details.\n"
    "- When it helps, summarize totals and patterns (e.g. how many trades, which "
    "sectors, overall buying vs selling sentiment) in a readable way.\n"
    "- Refer to people naturally by name and describe their trades in words "
    "(e.g. 'Representative Jane Doe reported purchasing NVIDIA stock in the "
    "$1,001–$15,000 range on March 4, 2025'), not as raw database fields.\n"
    "- It is fine to mention filer names, chamber, tickers, asset names, "
    "transaction dates, and dollar value ranges because they are meaningful to "
    "the user.\n"
    "- LATE FILINGS: A filing is 'late' under the STOCK Act when it is a Periodic "
    "Transaction Report (report_type PTR) filed MORE THAN 45 DAYS after the "
    "transaction date. Every context already includes computed 'is_late' and "
    "'days_late' fields — use them directly to answer late-filing questions. "
    "Never infer lateness from raw dates alone, and never claim a filing is late "
    "when its 'is_late' field is false. The 45-day clock runs ONLY from the "
    "transaction date to the filing date; ignore any 'notification'/'notified' "
    "dates that may appear in the text.\n"
    "- WATCHLIST: The user's watchlist (the members and tickers they monitor) is: "
    "{watchlist}. When the user asks about 'my watched members/tickers', restrict "
    "your answer to those entities and say so if none of the contexts match.\n"
    "- NEVER mention internal or technical provenance: no document IDs, doc_id, "
    "chunk text, 'Context 1/2/3', file paths, table/column names, row numbers, "
    "similarity scores, or how the data was retrieved. The user does not need "
    "this.\n"
    "- Do not claim access to anything outside the provided contexts.\n\n"
    "Formatting rules:\n"
    "- Respond in clean, concise Markdown.\n"
    "- Use short paragraphs and bullet points.\n"
    "- Bold only key figures (amounts, tickers, dates) sparingly.\n"
    "- Do not repeat or restate the question.\n"
    "- If the contexts do not contain the answer, say so in one plain sentence."
)


def _watchlist_summary(watchlist: Optional[Dict[str, List[str]]]) -> str:
    """Render the user's watchlist for the system prompt (or 'none')."""
    if not watchlist:
        return "none"
    members = watchlist.get("members") or []
    tickers = watchlist.get("tickers") or []
    parts: List[str] = []
    if members:
        parts.append("members: " + ", ".join(members))
    if tickers:
        parts.append("tickers: " + ", ".join(tickers))
    return "; ".join(parts) if parts else "none"


def build_system_prompt(
    allowed_chambers: List[str],
    watchlist: Optional[Dict[str, List[str]]] = None,
) -> str:
    """Build the system prompt embedding the caller's chambers and watchlist."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        allowed_chambers=", ".join(allowed_chambers),
        watchlist=_watchlist_summary(watchlist),
    )


def _late_fields(row: Dict[str, Any]) -> tuple:
    """Compute (days_late, is_late) for a disclosure row.

    Mirrors the backend rule in ``dashboard._late_filing_predicate``: a filing is
    late when it is a Periodic Transaction Report (report_type PTR, or NULL for
    backwards compatibility) filed more than 45 days after the transaction date.
    Returns ``(None, None)`` when the dates are missing or inconsistent.
    """
    filing = row.get("filing_date")
    trade = row.get("date")
    if not filing or not trade:
        return None, None
    try:
        f = _date.fromisoformat(str(filing)[:10])
        t = _date.fromisoformat(str(trade)[:10])
    except (ValueError, TypeError):
        return None, None
    days = (f - t).days
    if days < 0:
        return None, None
    report_type = (row.get("report_type") or "").upper()
    is_ptr = (not report_type) or ("PTR" in report_type)
    return days, bool(is_ptr and days > 45)


def _format_context(sources: List[Dict[str, Any]]) -> str:
    """Render retrieved rows into a compact, delimited context block."""
    blocks: List[str] = []
    for index, row in enumerate(sources, start=1):
        days_late, is_late = _late_fields(row)
        lines = [
            f"[Context {index}]",
            f"chamber: {row.get('chamber')}",
            f"filer_name: {row.get('filer_name')}",
            f"filing_date: {row.get('filing_date')}",
            f"report_type: {row.get('report_type')}",
            f"ticker: {row.get('ticker')}",
            f"asset_name: {row.get('asset_name')}",
            f"asset_category: {row.get('asset_category')}",
            f"action: {row.get('action')}",
            f"date: {row.get('date')}",
            f"value_range: {row.get('value_range')}",
            f"ownership: {row.get('ownership')}",
            f"days_late: {days_late if days_late is not None else 'N/A'}",
            f"is_late: {is_late if is_late is not None else 'N/A'}",
            f"comment: {row.get('comment')}",
            f"chunk_text: {row.get('chunk_text')}",
        ]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


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


def _build_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reduce retrieved rows to the grounded citation shape returned to clients.

    Each citation carries the metadata the UI renders on a source card: filer
    name, filing date, chamber, value range, and document id.
    """
    citations: List[Dict[str, Any]] = []
    for row in sources:
        days_late, is_late = _late_fields(row)
        citations.append(
            {
                "doc_id": row.get("doc_id"),
                "document_id": row.get("doc_id"),
                "filer_name": row.get("filer_name"),
                "chamber": row.get("chamber"),
                "filing_date": row.get("filing_date"),
                "ticker": row.get("ticker"),
                "asset_name": row.get("asset_name"),
                "action": row.get("action"),
                "date": row.get("date"),
                "value_range": row.get("value_range"),
                "days_late": days_late,
                "is_late": is_late,
                "similarity_score": row.get("similarity_score"),
            }
        )
    return citations


def synthesize(
    query: str,
    sources: List[Dict[str, Any]],
    allowed_chambers: List[str],
    user_id: Optional[str] = None,
    model: Optional[str] = None,
    watchlist: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Synthesize an answer from retrieved contexts via the LiteLLM Proxy.

    Returns a dict with ``answer`` (Markdown), ``sources`` (compact citations),
    and ``cost`` (USD as reported by the proxy, ``0.0`` if unavailable).
    """
    resolved_model = model or DEFAULT_MODEL
    system_prompt = build_system_prompt(allowed_chambers, watchlist)

    context = _format_context(sources)[:MAX_CONTEXT_CHARS]
    user_content = (
        "Use ONLY the disclosure contexts below to answer the question. "
        "If the contexts do not contain the answer, say so explicitly.\n\n"
        f"<<<CONTEXT_START>>>\n{context}\n<<<CONTEXT_END>>>\n\n"
        f"Question: {query}"
    )

    base = LITELLM_PROXY_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
        # Forward caller metadata for proxy audit logging.
        "X-User-Id": user_id or "unknown",
        "X-Allowed-Chambers": ",".join(allowed_chambers),
    }
    payload: Dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "metadata": {
            "user_id": user_id or "unknown",
            "allowed_chambers": allowed_chambers,
        },
    }

    logger.debug(
        "POST %s/v1/chat/completions model=%s sources=%d",
        base, resolved_model, len(sources),
    )
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{base}/v1/chat/completions", headers=headers, json=payload
        )
        if response.status_code >= 400:
            logger.error(
                "LiteLLM chat error HTTP %s for model %s: %s",
                response.status_code, resolved_model, response.text[:500],
            )
            raise RuntimeError(
                f"LiteLLM Proxy returned HTTP {response.status_code} for chat "
                f"model '{resolved_model}': {response.text[:1000]}"
            )
        data = response.json()
        cost = _extract_cost(response, data)
        usage = data.get("usage") if isinstance(data, dict) else None

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected LiteLLM chat response shape: {data}"
        ) from exc

    return {
        "answer": answer,
        "sources": _build_sources(sources),
        "cost": cost,
        "usage": usage or {},
    }


def synthesize_stream(
    query: str,
    sources: List[Dict[str, Any]],
    allowed_chambers: List[str],
    user_id: Optional[str] = None,
    model: Optional[str] = None,
    watchlist: Optional[Dict[str, List[str]]] = None,
) -> Iterator[str]:
    """Yield Server-Sent Events streaming the synthesized answer.

    Emits ``data: {"delta": "..."}`` events for each token chunk and a final
    ``data:. Raises ``RuntimeError`` on a proxy error.
    """
    resolved_model = model or DEFAULT_MODEL
    system_prompt = build_system_prompt(allowed_chambers, watchlist)
    context = _format_context(sources)[:MAX_CONTEXT_CHARS]
    user_content = (
        "Use ONLY the disclosure contexts below to answer the question. "
        "If the contexts do not contain the answer, say so explicitly.\n\n"
        f"<<<CONTEXT_START>>>\n{context}\n<<<CONTEXT_END>>>\n\n"
        f"Question: {query}"
    )

    base = LITELLM_PROXY_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
        "Content-Type": "application/json",
        "X-User-Id": user_id or "unknown",
        "X-Allowed-Chambers": ",".join(allowed_chambers),
    }
    payload: Dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "stream": True,
        "metadata": {
            "user_id": user_id or "unknown",
            "allowed_chambers": allowed_chambers,
        },
    }

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        with client.stream(
            "POST", f"{base}/v1/chat/completions", headers=headers, json=payload
        ) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", errors="replace")
                logger.error(
                    "LiteLLM chat stream error HTTP %s for model %s: %s",
                    response.status_code, resolved_model, body[:500],
                )
                raise RuntimeError(
                    f"LiteLLM Proxy returned HTTP {response.status_code} for chat "
                    f"model '{resolved_model}': {body[:1000]}"
                )
            for line in response.iter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                try:
                    obj = json.loads(data)
                    delta = obj["choices"][0]["delta"].get("content")
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                if delta:
                    yield f"data: {json.dumps({'delta': delta})}\n\n"
