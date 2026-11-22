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
