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


# ------------------------------------------------------------------------------
# Cluster health (FR-4.4)
# ------------------------------------------------------------------------------
async def test_cluster_health_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.get(f"{base_urls.admin}/api/v1/admin/health/cluster")
    assert resp.status_code == 401


async def test_cluster_health_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.admin}/api/v1/admin/health/cluster",
        headers=auth_header(user_token),
    )
    assert resp.status_code == 403


async def test_cluster_health_admin(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}/api/v1/admin/health/cluster",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "checked_at" in body
    services = {s["service"] for s in body["services"]}
    assert {"auth", "downloader", "parser", "vectorizer", "rag", "litellm"} <= services


# ------------------------------------------------------------------------------
# Audit log (FR-4.2)
# ------------------------------------------------------------------------------
async def test_audit_log_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.get(f"{base_urls.admin}/api/v1/admin/audit-log")
    assert resp.status_code == 401


async def test_audit_log_admin(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.admin}/api/v1/admin/audit-log",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "entries" in body and isinstance(body["entries"], list)


# ------------------------------------------------------------------------------
# Pipeline orchestration (FR-4.1)
# ------------------------------------------------------------------------------
async def test_pipeline_trigger_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.admin}/api/v1/admin/pipeline/parser/trigger", json={}
    )
    assert resp.status_code == 401


async def test_pipeline_trigger_unknown_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.admin}/api/v1/admin/pipeline/not-a-service/trigger",
        headers=auth_header(admin_token),
        json={},
    )
    assert resp.status_code == 404


async def test_retry_unknown_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.admin}/api/v1/admin/pipeline/jobs/not-a-service/{uuid.uuid4()}/retry",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404


# ------------------------------------------------------------------------------
# Schedules (FR-4.1)
# ------------------------------------------------------------------------------
async def test_schedule_crud(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    headers = auth_header(admin_token)
    resp = await client.post(
        f"{base_urls.admin}/api/v1/admin/pipeline/schedule",
        headers=headers,
        json={"service": "parser", "interval_minutes": 60},
    )
    assert resp.status_code == 201
    schedule = resp.json()
    assert schedule["service"] == "parser"
    # List
    resp = await client.get(
        f"{base_urls.admin}/api/v1/admin/pipeline/schedule", headers=headers
    )
    assert resp.status_code == 200
    assert any(s["id"] == schedule["id"] for s in resp.json()["schedules"])
    # Delete
    resp = await client.delete(
        f"{base_urls.admin}/api/v1/admin/pipeline/schedule/{schedule['id']}",
        headers=headers,
    )
    assert resp.status_code == 204


async def test_schedule_invalid_service(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.admin}/api/v1/admin/pipeline/schedule",
        headers=auth_header(admin_token),
        json={"service": "not-a-service", "interval_minutes": 60},
    )
    assert resp.status_code == 404
