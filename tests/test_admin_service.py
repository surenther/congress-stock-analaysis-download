#!/usr/bin/env python3
"""
Tests for the admin-service (port 8515).

Covers: health, admin-only enforcement on every jobs route, unified job list
with filters/pagination, summary aggregation, and 404 handling.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract

JOBS = "/api/v1/jobs"


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.admin}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_jobs_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.admin}{JOBS}")
    assert resp.status_code == 401


async def test_jobs_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(f"{base_urls.admin}{JOBS}", headers=auth_header(user_token))
    assert resp.status_code == 403


async def test_jobs_list_admin(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}", headers=auth_header(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(["total", "limit", "offset", "jobs"]).issubset(body.keys())
    assert isinstance(body["jobs"], list)


async def test_jobs_list_filter_by_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}",
        params={"service": "parser", "limit": 5},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    for job in resp.json()["jobs"]:
        assert job["service"] == "parser"


async def test_jobs_list_filter_by_status(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}",
        params={"status": "COMPLETED", "limit": 5},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    for job in resp.json()["jobs"]:
        assert job["status"] == "COMPLETED"


async def test_jobs_list_invalid_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}",
        params={"service": "not-a-service"},
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_jobs_summary_admin(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}/summary", headers=auth_header(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(["total", "by_service", "by_status", "breakdown"]).issubset(body.keys())


async def test_jobs_summary_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}/summary", headers=auth_header(user_token)
    )
    assert resp.status_code == 403


async def test_job_detail_unknown_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}/not-a-service/{uuid.uuid4()}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_job_detail_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}/parser/{uuid.uuid4()}",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_job_items_unknown_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}/not-a-service/{uuid.uuid4()}/items",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


async def test_job_items_unknown_job(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}{JOBS}/downloader/{uuid.uuid4()}/items",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404
