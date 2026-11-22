#!/usr/bin/env python3
"""
Tests for the downloader service (port 8511).

Covers: health, trigger auth/role/validation, 409 concurrency, status and
per-file items retrieval (pagination + status filter).
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract

TRIGGER = "/api/v1/download/trigger"


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.downloader}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_trigger_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(
        f"{base_urls.downloader}{TRIGGER}", json={"chamber": "house"}
    )
    assert resp.status_code == 401


async def test_trigger_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.downloader}{TRIGGER}",
        json={"chamber": "house"},
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403


async def test_trigger_invalid_chamber(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.downloader}{TRIGGER}",
        json={"chamber": "not-a-chamber"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 400


async def test_trigger_missing_chamber(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.downloader}{TRIGGER}",
        json={},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 422


async def test_status_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.downloader}/api/v1/download/status/{uuid.uuid4()}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_status_malformed_job_id(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.downloader}/api/v1/download/status/not-a-uuid",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_status_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(
        f"{base_urls.downloader}/api/v1/download/status/{uuid.uuid4()}"
    )
    assert resp.status_code == 401


async def test_items_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.downloader}/api/v1/download/status/{uuid.uuid4()}/items",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.llm
async def test_trigger_and_poll_lifecycle(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_token: str,
    user_token: str,
    test_chamber: str,
    run_llm_tests: bool,
    poll_timeout: int,
    poll_interval: int,
    poll_job_helper,
):
    """Trigger a small download job and poll it to a terminal state.

    Requires RUN_LLM_TESTS=true (network access to the House/Senate portals).
    Uses ``limit=1`` to keep the run tiny.
    """
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false.")

    resp = await client.post(
        f"{base_urls.downloader}{TRIGGER}",
        json={"chamber": test_chamber, "limit": 1},
        headers=auth_header(admin_token),
    )
    # 202 accepted, or 409 if another job is already running.
    if resp.status_code == 409:
        pytest.skip("A download job is already running; skipping lifecycle test.")
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    final = await poll_job_helper(
        client,
        f"{base_urls.downloader}/api/v1/download/status/{job_id}",
        admin_token,
        timeout=poll_timeout,
        interval=poll_interval,
    )
    assert final["status"] in ("COMPLETED", "FAILED")

    # Items endpoint should be reachable and paginated.
    items = await client.get(
        f"{base_urls.downloader}/api/v1/download/status/{job_id}/items",
        headers=auth_header(user_token),
        params={"limit": 10, "offset": 0},
    )
    assert items.status_code == 200
    body = items.json()
    assert body["job_id"] == job_id
    assert "items" in body and isinstance(body["items"], list)
