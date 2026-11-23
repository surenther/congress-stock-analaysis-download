#!/usr/bin/env python3
"""
Tests for the auth-service 2FA, password-lifecycle, refresh-token, and
admin user-management endpoints (port 8512).

These are contract tests against a running stack. Tests that need a specific
account skip when the corresponding credentials are not configured in
``tests/.env.test``.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import BaseURLs, Credentials, auth_header

pytestmark = pytest.mark.contract


# ------------------------------------------------------------------------------
# Login flow
# ------------------------------------------------------------------------------
async def test_login_returns_next_step(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_credentials: Credentials,
):
    """Login returns either tokens or a next-step indicator (never both)."""
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
    assert "mfa_required" in body
    if body.get("access_token"):
        assert body.get("mfa_token") is None
    else:
        assert body.get("mfa_token")
        assert (
            body.get("mfa_required")
            or body.get("must_setup_2fa")
            or body.get("must_change_password")
        )


async def test_login_invalid_password_generic(
    client: httpx.AsyncClient,
    base_urls: BaseURLs,
    admin_credentials: Credentials,
):
    if not admin_credentials.configured:
        pytest.skip("TEST_ADMIN_USERNAME/PASSWORD not configured.")
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/login",
        json={"username": admin_credentials.username, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


# ------------------------------------------------------------------------------
# MFA endpoints
# ------------------------------------------------------------------------------
async def test_mfa_verify_rejects_bad_token(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/mfa/verify",
        json={"mfa_token": "not.a.real.token", "code": "123456"},
    )
    assert resp.status_code == 401


async def test_mfa_setup_rejects_bad_token(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/mfa/setup",
        json={"mfa_token": "not.a.real.token"},
    )
    assert resp.status_code == 401


async def test_mfa_enable_rejects_bad_token(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/mfa/enable",
        json={"mfa_token": "not.a.real.token", "code": "123456"},
    )
    assert resp.status_code == 401


async def test_mfa_disable_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/mfa/disable",
        json={"password": "x", "code": "123456"},
    )
    assert resp.status_code == 401


# ------------------------------------------------------------------------------
# Password lifecycle
# ------------------------------------------------------------------------------
async def test_change_password_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "y"},
    )
    assert resp.status_code == 401


async def test_forgot_password_always_accepted(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    """No user enumeration: unknown emails still return 202."""
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/forgot-password",
        json={"email": "nobody-xyz@example.invalid"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


async def test_reset_password_rejects_bad_token(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "Str0ngPassword!"},
    )
    assert resp.status_code == 400


# ------------------------------------------------------------------------------
# Refresh / logout
# ------------------------------------------------------------------------------
async def test_refresh_rejects_bad_token(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/refresh",
        json={"refresh_token": "not-a-real-refresh-token"},
    )
    assert resp.status_code == 401


async def test_logout_is_idempotent(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.post(
        f"{base_urls.auth}/api/v1/auth/logout",
        json={"refresh_token": "not-a-real-refresh-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ------------------------------------------------------------------------------
# /me
# ------------------------------------------------------------------------------
async def test_me_includes_mfa_fields(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.auth}/api/v1/auth/me", headers=auth_header(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "mfa_enabled" in body
    assert "must_change_password" in body


# ------------------------------------------------------------------------------
# Admin user management
# ------------------------------------------------------------------------------
async def test_admin_users_requires_auth(
    client: httpx.AsyncClient, base_urls: BaseURLs
):
    resp = await client.get(f"{base_urls.auth}/api/v1/admin/users")
    assert resp.status_code == 401


async def test_admin_users_forbidden_for_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_token: str
):
    resp = await client.get(
        f"{base_urls.auth}/api/v1/admin/users", headers=auth_header(user_token)
    )
    assert resp.status_code == 403


async def test_admin_users_list_with_admin(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.auth}/api/v1/admin/users", headers=auth_header(admin_token)
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_admin_create_user_validation(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    """A too-short username is rejected with 422."""
    resp = await client.post(
        f"{base_urls.auth}/api/v1/admin/users",
        headers=auth_header(admin_token),
        json={"username": "ab"},
    )
    assert resp.status_code == 422
