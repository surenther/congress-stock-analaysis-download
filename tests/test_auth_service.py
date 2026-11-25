#!/usr/bin/env python3
"""
Tests for the auth-service (port 8512).

Covers: health, login (valid/invalid/missing/form), token verification via
``/api/v1/auth/me``, and the login rate limiter.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import BaseURLs, Credentials, auth_header

pytestmark = pytest.mark.contract


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.auth}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_login_valid_admin(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_credentials: Credentials,
):
    if not admin_credentials.configured:
        pytest.skip("TEST_ADMIN_USERNAME/PASSWORD not configured.")
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/login",
        json={
            "username": admin_credentials.username,
            "password": admin_credentials.password,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]


async def test_login_invalid_password(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_credentials: Credentials,
):
    if not admin_credentials.configured:
        pytest.skip("TEST_ADMIN_USERNAME/PASSWORD not configured.")
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/login",
        json={
            "username": admin_credentials.username,
            "password": "definitely-not-the-password",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_unknown_user(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/login",
        json={"username": "no-such-user-xyz", "password": "whatever"},
    )
    assert resp.status_code == 401


async def test_login_missing_fields(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/login",
        json={"username": "someone"},
    )
    assert resp.status_code == 422


async def test_login_form_body(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_credentials: Credentials,
):
    """The endpoint also accepts OAuth2-style form bodies."""
    if not admin_credentials.configured:
        pytest.skip("TEST_ADMIN_USERNAME/PASSWORD not configured.")
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/login",
        data={
            "username": admin_credentials.username,
            "password": admin_credentials.password,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_me_with_valid_token(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.auth}/api/v1/auth/me", headers=auth_header(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"]
    assert isinstance(body["roles"], list)
    assert isinstance(body["allowed_chambers"], list)
    assert "is_active" in body


async def test_me_without_token(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.auth}/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_malformed_token(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(
        f"{base_urls.auth}/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert resp.status_code == 401


@pytest.mark.slow
async def test_login_rate_limit(client: httpx.AsyncClient, base_urls: BaseURLs):
    """Repeated failed logins eventually return 429.

    Marked ``slow`` because it deliberately exhausts the per-IP login budget
    (default 10 attempts / 300s), which would otherwise affect other tests.
    """
    username = "rate-limit-probe-user"
    statuses = []
    for _ in range(15):
        resp = await client.post(
            f"{base_urls.auth}/api/v1/auth/login",
            json={"username": username, "password": "wrong"},
        )
        statuses.append(resp.status_code)
        if resp.status_code == 429:
            break
    assert 429 in statuses, f"Expected a 429 within 15 attempts, got {statuses}"


# ------------------------------------------------------------------------------
# Admin bulk user actions
# ------------------------------------------------------------------------------
async def test_bulk_action_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/bulk",
        json={"user_ids": ["00000000-0000-0000-0000-000000000000"], "action": "activate"},
    )
    assert resp.status_code == 401


async def test_bulk_action_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/bulk",
        headers=auth_header(user_token),
        json={"user_ids": ["00000000-0000-0000-0000-000000000000"], "action": "activate"},
    )
    assert resp.status_code == 403


async def test_bulk_action_invalid_action(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/bulk",
        headers=auth_header(admin_token),
        json={"user_ids": ["00000000-0000-0000-0000-000000000000"], "action": "nope"},
    )
    assert resp.status_code == 422


async def test_bulk_action_set_chambers_requires_chambers(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/bulk",
        headers=auth_header(admin_token),
        json={
            "user_ids": ["00000000-0000-0000-0000-000000000000"],
            "action": "set-chambers",
        },
    )
    assert resp.status_code == 422


async def test_bulk_action_unknown_user_reports_failure(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/bulk",
        headers=auth_header(admin_token),
        json={
            "user_ids": ["00000000-0000-0000-0000-000000000000"],
            "action": "activate",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested"] == 1
    assert body["succeeded"] == 0
    assert body["failed"] == 1


# ------------------------------------------------------------------------------
# Admin reset 2FA
# ------------------------------------------------------------------------------
async def test_reset_2fa_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/00000000-0000-0000-0000-000000000000/reset-2fa"
    )
    assert resp.status_code == 401


async def test_reset_2fa_unknown_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users/00000000-0000-0000-0000-000000000000/reset-2fa",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 404
