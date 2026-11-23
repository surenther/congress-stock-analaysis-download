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
    "You are an AI financial analyst. Answer the user's question using ONLY the "
    "provided disclosure contexts. Explicitly cite filers, tickers, dates, and "
    "amounts. You are operating under strict chamber permissions for: "
    "{allowed_chambers}.\n\n"
    "Formatting rules:\n"
    "- Respond in clean, concise Markdown.\n"
    "- Use short paragraphs and bullet points.\n"
    "- Avoid bold emphasis except for key figures (amounts, tickers, dates).\n"
    "- Do not repeat or restate the question.\n"
    "- If the contexts do not contain the answer, say so in one sentence."
)


def build_system_prompt(allowed_chambers: List[str]) -> str:
    """Build the system prompt embedding the caller's allowed chambers."""
    return SYSTEM_PROMPT_TEMPLATE.format(
        allowed_chambers=", ".join(allowed_chambers)
    )


def _format_context(sources: List[Dict[str, Any]]) -> str:
    """Render retrieved rows into a compact, delimited context block."""
    blocks: List[str] = []
    for index, row in enumerate(sources, start=1):
        lines = [
            f"[Context {index}]",
            f"doc_id: {row.get('doc_id')}",
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
) -> Dict[str, Any]:
    """Synthesize an answer from retrieved contexts via the LiteLLM Proxy.

    Returns a dict with ``answer`` (Markdown), ``sources`` (compact citations),
    and ``cost`` (USD as reported by the proxy, ``0.0`` if unavailable).
    """
    resolved_model = model or DEFAULT_MODEL
    system_prompt = build_system_prompt(allowed_chambers)

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
) -> Iterator[str]:
    """Yield Server-Sent Events streaming the synthesized answer.

    Emits ``data: {"delta": "..."}`` events for each token chunk and a final
    ``data: [DONE]`` event. Raises ``RuntimeError`` on a proxy error.
    """
    resolved_model = model or DEFAULT_MODEL
    system_prompt = build_system_prompt(allowed_chambers)
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
