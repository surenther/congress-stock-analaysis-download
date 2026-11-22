#!/usr/bin/env python3
"""
Tests for the parser service (port 8513).

Covers: health, bulk/single trigger auth/role/validation, status, per-document
items, and parsed-document retrieval.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract

TRIGGER = "/api/v1/parse/trigger"


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.parser}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_trigger_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(f"{base_urls.parser}{TRIGGER}", json={})
    assert resp.status_code == 401


async def test_trigger_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.parser}{TRIGGER}", json={}, headers=auth_header(user_token)
    )
    assert resp.status_code == 403


async def test_trigger_bulk_invalid_chamber(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.parser}{TRIGGER}",
        json={"chamber": "not-a-chamber"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


async def test_trigger_single_invalid_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.parser}{TRIGGER}",
        json={"file_path": "house_rep/2026/x/1.pdf", "doc_id": "../../etc/passwd"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


async def test_trigger_single_invalid_chamber(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.parser}{TRIGGER}",
        json={
            "file_path": "house_rep/2026/x/12345.pdf",
            "doc_id": "12345",
            "chamber": "not-a-chamber",
        },
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


async def test_status_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.parser}/api/v1/parse/status/{uuid.uuid4()}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_status_malformed_job_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.parser}/api/v1/parse/status/not-a-uuid",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_status_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.parser}/api/v1/parse/status/{uuid.uuid4()}")
    assert resp.status_code == 401


async def test_items_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.parser}/api/v1/parse/status/{uuid.uuid4()}/items",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


async def test_document_invalid_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.parser}/api/v1/parse/document/..%2F..%2Fetc%2Fpasswd",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


async def test_document_unknown_doc_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.parser}/api/v1/parse/document/999999999",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


async def test_document_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.parser}/api/v1/parse/document/12345")
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
    """Trigger a tiny bulk parse job and poll to a terminal state."""
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false.")

    resp = await client.post(
        f"{base_urls.parser}{TRIGGER}",
        json={"limit": 1},
        headers=auth_header(admin_token),
    )
    if resp.status_code == 409:
        pytest.skip("A parse job is already running; skipping lifecycle test.")
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    final = await poll_job_helper(
        client,
        f"{base_urls.parser}/api/v1/parse/status/{job_id}",
        admin_token,
        timeout=poll_timeout,
        interval=poll_interval,
    )
    assert final["status"] in ("COMPLETED", "FAILED")
    assert "succeeded" in final and "failed" in final


@pytest.mark.integration
async def test_document_retrieval(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    user_token: str,
    test_doc_id: str,
):
    """Fetch a known parsed document (requires TEST_DOC_ID to be set)."""
    if not test_doc_id:
        pytest.skip("TEST_DOC_ID not configured.")
    resp = await client.get(
        f"{base_urls.parser}/api/v1/parse/document/{test_doc_id}",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
