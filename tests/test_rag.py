#!/usr/bin/env python3
"""
Tests for the RAG service (port 8516).

Covers: health, auth/role enforcement, Chamber-Based Access Control (CBAC)
guardrails (403 before any LLM call), structured search, and request validation.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract

QUERY = "/api/v1/rag/query"
SEARCH = "/api/v1/rag/search-structured"


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.rag}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_query_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(f"{base_urls.rag}{QUERY}", json={"prompt": "hello"})
    assert resp.status_code == 401


async def test_query_empty_prompt_validation(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.rag}{QUERY}",
        json={"prompt": ""},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 422


async def test_query_top_k_out_of_range(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.rag}{QUERY}",
        json={"prompt": "tech stocks", "top_k": 999},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 422


# ------------------------------------------------------------------------------
# CBAC guardrails — these return 403 BEFORE any embedding/LLM call, so they are
# fast contract tests (no LLM spend).
# ------------------------------------------------------------------------------
async def test_cbac_house_user_cannot_query_senate(
    client: httpx.AsyncClient, base_urls: BaseURLs, house_token: str
):
    resp = await client.post(
        f"{base_urls.rag}{QUERY}",
        json={"prompt": "Senate trades in NVDA", "filters": {"chamber": "Senate"}},
        headers=auth_header(house_token),
    )
    assert resp.status_code == 403


async def test_cbac_senate_user_cannot_query_house(
    client: httpx.AsyncClient, base_urls: BaseURLs, senate_token: str
):
    resp = await client.post(
        f"{base_urls.rag}{QUERY}",
        json={"prompt": "House trades in AAPL", "filters": {"chamber": "House"}},
        headers=auth_header(senate_token),
    )
    assert resp.status_code == 403


async def test_cbac_structured_house_user_cannot_query_senate(
    client: httpx.AsyncClient, base_urls: BaseURLs, house_token: str
):
    resp = await client.post(
        f"{base_urls.rag}{SEARCH}",
        json={"filters": {"chamber": "Senate"}},
        headers=auth_header(house_token),
    )
    assert resp.status_code == 403


async def test_cbac_structured_senate_user_cannot_query_house(
    client: httpx.AsyncClient, base_urls: BaseURLs, senate_token: str
):
    resp = await client.post(
        f"{base_urls.rag}{SEARCH}",
        json={"filters": {"chamber": "House"}},
        headers=auth_header(senate_token),
    )
    assert resp.status_code == 403


async def test_structured_search_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(f"{base_urls.rag}{SEARCH}", json={})
    assert resp.status_code == 401


# ------------------------------------------------------------------------------
# Integration — these hit the database (and, for /query, the LLM).
# ------------------------------------------------------------------------------
@pytest.mark.integration
async def test_structured_search_within_grant(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    """A user with both chambers can run a structured search (no LLM)."""
    resp = await client.post(
        f"{base_urls.rag}{SEARCH}",
        json={"top_k": 5},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "user_chamber_access" in body
    assert "count" in body and "results" in body


@pytest.mark.integration
@pytest.mark.llm
async def test_rag_query_end_to_end(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_token: str,
    run_llm_tests: bool,
):
    """Full RAG synthesis (embeddings + SQL + LLM). Requires RUN_LLM_TESTS=true."""
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false.")
    resp = await client.post(
        f"{base_urls.rag}{QUERY}",
        json={"prompt": "Which members bought tech stocks?", "top_k": 5},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"]
    assert isinstance(body["answer"], str)
    assert isinstance(body["sources"], list)
    assert isinstance(body["user_chamber_access"], list)


# ------------------------------------------------------------------------------
# Structured 403 contract (FR-3.4)
# ------------------------------------------------------------------------------
async def test_cbac_403_structured_contract(
    client: httpx.AsyncClient, base_urls: BaseURLs, house_token: str
):
    """A cross-chamber request returns a machine-readable 403 body."""
    resp = await client.post(
        f"{base_urls.rag}{SEARCH}",
        json={"filters": {"chamber": "Senate"}},
        headers=auth_header(house_token),
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["code"] == "CHAMBER_SCOPE_VIOLATION"
    assert detail["requested_chamber"] == "Senate"
    assert "House" in detail["allowed_chambers"]


# ------------------------------------------------------------------------------
# Streaming (FR-3.1)
# ------------------------------------------------------------------------------
async def test_stream_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(
        f"{base_urls.rag}/api/v1/rag/query/stream", json={"prompt": "hello"}
    )
    assert resp.status_code == 401


async def test_stream_cbac_guardrail(
    client: httpx.AsyncClient, base_urls: BaseURLs, house_token: str
):
    resp = await client.post(
        f"{base_urls.rag}/api/v1/rag/query/stream",
        json={"prompt": "Senate trades", "filters": {"chamber": "Senate"}},
        headers=auth_header(house_token),
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------------------
# Export (FR-5.2)
# ------------------------------------------------------------------------------
async def test_export_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(f"{base_urls.rag}/api/v1/rag/export", json={})
    assert resp.status_code == 401


@pytest.mark.integration
async def test_export_csv(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.rag}/api/v1/rag/export",
        json={"format": "csv", "top_k": 5},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


@pytest.mark.integration
async def test_export_pdf(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.rag}/api/v1/rag/export",
        json={"format": "pdf", "top_k": 5},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ------------------------------------------------------------------------------
# Citation fields (FR-3.3)
# ------------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.llm
async def test_query_citations_have_grounding_fields(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_token: str,
    run_llm_tests: bool,
):
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false.")
    resp = await client.post(
        f"{base_urls.rag}{QUERY}",
        json={"prompt": "Which members bought tech stocks?", "top_k": 5},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200, resp.text
    sources = resp.json()["sources"]
    if sources:
        first = sources[0]
        for field in ("doc_id", "filer_name", "chamber", "filing_date", "value_range"):
            assert field in first
