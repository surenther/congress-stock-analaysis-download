#!/usr/bin/env python3
"""
Tests for the vectorizer service (port 8514).

Covers: health, single/bulk trigger auth/role/validation, status, per-document
items, and stored-embedding metadata retrieval.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract

TRIGGER = "/api/v1/vectorize/trigger"
TRIGGER_BULK = "/api/v1/vectorize/trigger-bulk"


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.vectorizer}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_trigger_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(f"{base_urls.vectorizer}{TRIGGER}", json={"doc_id": "1"})
    assert resp.status_code == 401


async def test_trigger_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER}",
        json={"doc_id": "1"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403


async def test_trigger_missing_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER}", json={}, headers=auth_header(admin_token)
    )
    assert resp.status_code == 422


async def test_trigger_invalid_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER}",
        json={"doc_id": "../../etc/passwd"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


async def test_trigger_unknown_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER}",
        json={"doc_id": "999999999"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_trigger_bulk_invalid_chamber(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER_BULK}",
        json={"chamber": "not-a-chamber"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


async def test_trigger_bulk_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER_BULK}",
        json={"chamber": "all"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403


async def test_status_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.vectorizer}/api/v1/vectorize/status/{uuid.uuid4()}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_status_malformed_job_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.vectorizer}/api/v1/vectorize/status/not-a-uuid",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_items_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.vectorizer}/api/v1/vectorize/status/{uuid.uuid4()}/items",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


async def test_document_invalid_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.vectorizer}/api/v1/vectorize/document/..%2F..%2Fetc%2Fpasswd",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 400


async def test_document_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.vectorizer}/api/v1/vectorize/document/12345")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.llm
async def test_bulk_trigger_and_poll(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_token: str,
    run_llm_tests: bool,
    poll_timeout: int,
    poll_interval: int,
    poll_job_helper,
):
    """Trigger a tiny bulk vectorization job and poll to a terminal state."""
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false.")

    resp = await client.post(
        f"{base_urls.vectorizer}{TRIGGER_BULK}",
        json={"chamber": "all", "limit": 1},
        headers=auth_header(admin_token),
    )
    if resp.status_code == 409:
        pytest.skip("A vectorization job is already running; skipping lifecycle test.")
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    final = await poll_job_helper(
        client,
        f"{base_urls.vectorizer}/api/v1/vectorize/status/{job_id}",
        admin_token,
        timeout=poll_timeout,
        interval=poll_interval,
    )
    assert final["status"] in ("COMPLETED", "FAILED")


@pytest.mark.integration
async def test_document_embeddings_retrieval(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    user_token: str,
    test_doc_id: str,
):
    """Fetch stored embedding metadata for a known doc (requires TEST_DOC_ID)."""
    if not test_doc_id:
        pytest.skip("TEST_DOC_ID not configured.")
    resp = await client.get(
        f"{base_urls.vectorizer}/api/v1/vectorize/document/{test_doc_id}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_id"] == test_doc_id
    assert "vectorized" in body and "item_count" in body
