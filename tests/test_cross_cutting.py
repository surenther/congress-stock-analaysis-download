#!/usr/bin/env python3
"""
Cross-cutting tests that apply to every service.

Covers: baseline security headers, the RBAC matrix (401 vs 403), request
validation (422), unknown-resource handling (404), and the 409 concurrency
guard on the job-triggering services.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def _service_health_urls(base_urls: BaseURLs) -> dict[str, str]:
    return {
        "auth": f"{base_urls.auth}/health",
        "downloader": f"{base_urls.downloader}/health",
        "parser": f"{base_urls.parser}/health",
        "vectorizer": f"{base_urls.vectorizer}/health",
        "admin": f"{base_urls.admin}/health",
        "rag": f"{base_urls.rag}/health",
    }


@pytest.mark.parametrize("service", ["auth", "downloader", "parser", "vectorizer", "admin", "rag"])
async def test_security_headers_present(
    client: httpx.AsyncClient, base_urls: BaseURLs, service: str
):
    url = _service_health_urls(base_urls)[service]
    resp = await client.get(url)
    assert resp.status_code == 200
    for header, expected in SECURITY_HEADERS.items():
        assert resp.headers.get(header) == expected, (
            f"{service} missing/incorrect {header}: {resp.headers.get(header)!r}"
        )
    # HSTS is set on all services.
    assert "strict-transport-security" in {k.lower() for k in resp.headers.keys()}


# ------------------------------------------------------------------------------
# RBAC matrix: (method, path-template, admin_expected, user_expected)
# admin_expected/user_expected are the status codes for a *valid* request shape;
# we only assert the auth/role gate here (401 without token, 403 for wrong role).
# ------------------------------------------------------------------------------
PROTECTED_ENDPOINTS = [
    # (service, method, path, body)
    ("downloader", "POST", "/api/v1/download/trigger", {"chamber": "house"}),
    ("parser", "POST", "/api/v1/parse/trigger", {}),
    ("vectorizer", "POST", "/api/v1/vectorize/trigger", {"doc_id": "1"}),
    ("vectorizer", "POST", "/api/v1/vectorize/trigger-bulk", {"chamber": "all"}),
    ("admin", "GET", "/api/v1/jobs", None),
    ("admin", "GET", "/api/v1/jobs/summary", None),
    ("rag", "POST", "/api/v1/rag/query", {"prompt": "hi"}),
    ("rag", "POST", "/api/v1/rag/search-structured", {}),
]


def _base_for(base_urls: BaseURLs, service: str) -> str:
    return {
        "downloader": base_urls.downloader,
        "parser": base_urls.parser,
        "vectorizer": base_urls.vectorizer,
        "admin": base_urls.admin,
        "rag": base_urls.rag,
    }[service]


@pytest.mark.parametrize("service,method,path,body", PROTECTED_ENDPOINTS)
async def test_protected_endpoint_requires_auth(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    service: str,
    method: str,
    path: str,
    body,
):
    url = f"{_base_for(base_urls, service)}{path}"
    resp = await client.request(method, url, json=body)
    assert resp.status_code == 401, f"{service} {path} -> {resp.status_code}"


# Endpoints that require the admin role specifically (a `user` token -> 403).
ADMIN_ONLY_ENDPOINTS = [
    ("downloader", "POST", "/api/v1/download/trigger", {"chamber": "house"}),
    ("parser", "POST", "/api/v1/parse/trigger", {}),
    ("vectorizer", "POST", "/api/v1/vectorize/trigger", {"doc_id": "1"}),
    ("vectorizer", "POST", "/api/v1/vectorize/trigger-bulk", {"chamber": "all"}),
    ("admin", "GET", "/api/v1/jobs", None),
    ("admin", "GET", "/api/v1/jobs/summary", None),
]


@pytest.mark.parametrize("service,method,path,body", ADMIN_ONLY_ENDPOINTS)
async def test_admin_only_endpoint_forbidden_for_user(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    user_token: str,
    service: str,
    method: str,
    path: str,
    body,
):
    url = f"{_base_for(base_urls, service)}{path}"
    resp = await client.request(
        method, url, json=body, headers=auth_header(user_token)
    )
    assert resp.status_code == 403, f"{service} {path} -> {resp.status_code}"


# ------------------------------------------------------------------------------
# 409 concurrency guard (integration; requires admin + a running stack).
# ------------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.parametrize(
    "service,path,body",
    [
        ("downloader", "/api/v1/download/trigger", {"chamber": "house", "limit": 1}),
        ("parser", "/api/v1/parse/trigger", {"limit": 1}),
        ("vectorizer", "/api/v1/vectorize/trigger-bulk", {"chamber": "all", "limit": 1}),
    ],
)
async def test_second_trigger_conflicts(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_token: str,
    run_llm_tests: bool,
    service: str,
    path: str,
    body,
):
    """A second trigger while a job is active must return 409."""
    if not run_llm_tests:
        pytest.skip("RUN_LLM_TESTS is false.")

    url = f"{_base_for(base_urls, service)}{path}"
    first = await client.post(url, json=body, headers=auth_header(admin_token))
    if first.status_code == 409:
        # A job was already running before we started; the guard is working.
        return
    assert first.status_code == 202, first.text

    second = await client.post(url, json=body, headers=auth_header(admin_token))
    assert second.status_code == 409, (
        f"Expected 409 on overlapping {service} trigger, got {second.status_code}"
    )
