#!/usr/bin/env python3
"""
Shared pytest fixtures for the Congressional Disclosures API test suite.

Loads credentials from ``tests/.env.test`` (git-ignored), exposes base-URL and
token fixtures, provides an async HTTP client, and offers a job-polling helper.

Run modes
---------
* Default (``RUN_LLM_TESTS=false``): only fast contract/negative tests run.
* Integration (``RUN_LLM_TESTS=true``): tests marked ``llm``/``slow`` also run
  and actually trigger jobs against the running stack.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import jwt
import pytest
import pytest_asyncio
from dotenv import load_dotenv

# ------------------------------------------------------------------------------
# Load tests/.env.test (falls back to the committed example so imports work
# even before the user pastes credentials — tests that need values will skip).
# ------------------------------------------------------------------------------
_TESTS_DIR = Path(__file__).resolve().parent
_ENV_TEST = _TESTS_DIR / ".env.test"
_ENV_EXAMPLE = _TESTS_DIR / ".env.test.example"

if _ENV_TEST.exists():
    load_dotenv(_ENV_TEST, override=True)
elif _ENV_EXAMPLE.exists():
    load_dotenv(_ENV_EXAMPLE, override=False)


# ------------------------------------------------------------------------------
# Configuration helpers
# ------------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, str(default)).lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class BaseURLs:
    """Resolved host-side base URLs for every service."""

    auth: str
    downloader: str
    parser: str
    vectorizer: str
    admin: str
    rag: str
    analytics: str


@dataclass(frozen=True)
class Credentials:
    """A username/password pair (and optional TOTP secret) for token acquisition."""

    username: str
    password: str
    totp_secret: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password)


# ------------------------------------------------------------------------------
# Session-scoped configuration fixtures
# ------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def base_urls() -> BaseURLs:
    """Host-side base URLs for all services (from tests/.env.test)."""
    return BaseURLs(
        auth=_env("AUTH_BASE_URL", "http://localhost:8512"),
        downloader=_env("DOWNLOADER_BASE_URL", "http://localhost:8511"),
        parser=_env("PARSER_BASE_URL", "http://localhost:8513"),
        vectorizer=_env("VECTORIZER_BASE_URL", "http://localhost:8514"),
        admin=_env("ADMIN_BASE_URL", "http://localhost:8515"),
        rag=_env("RAG_BASE_URL", "http://localhost:8516"),
        analytics=_env("ANALYTICS_BASE_URL", "http://localhost:8517"),
    )


@pytest.fixture(scope="session")
def run_llm_tests() -> bool:
    """Whether LLM-spending integration tests should run."""
    return _env_bool("RUN_LLM_TESTS", False)


@pytest.fixture(scope="session")
def test_doc_id() -> str:
    """A known parsed doc_id, or empty string if not configured."""
    return _env("TEST_DOC_ID")


@pytest.fixture(scope="session")
def test_chamber() -> str:
    """Chamber used for trigger tests (house/senate/all)."""
    return _env("TEST_CHAMBER", "house") or "house"


@pytest.fixture(scope="session")
def poll_timeout() -> int:
    return _env_int("JOB_POLL_TIMEOUT_SECONDS", 120)


@pytest.fixture(scope="session")
def poll_interval() -> int:
    return _env_int("JOB_POLL_INTERVAL_SECONDS", 2)


@pytest.fixture(scope="session")
def admin_credentials() -> Credentials:
    return Credentials(
        _env("TEST_ADMIN_USERNAME"),
        _env("TEST_ADMIN_PASSWORD"),
        _env("TEST_ADMIN_TOTP_SECRET"),
    )


@pytest.fixture(scope="session")
def user_credentials() -> Credentials:
    return Credentials(
        _env("TEST_USER_USERNAME"),
        _env("TEST_USER_PASSWORD"),
        _env("TEST_USER_TOTP_SECRET"),
    )


@pytest.fixture(scope="session")
def house_credentials() -> Credentials:
    return Credentials(
        _env("TEST_HOUSE_USER_USERNAME"),
        _env("TEST_HOUSE_USER_PASSWORD"),
        _env("TEST_HOUSE_USER_TOTP_SECRET"),
    )


@pytest.fixture(scope="session")
def senate_credentials() -> Credentials:
    return Credentials(
        _env("TEST_SENATE_USER_USERNAME"),
        _env("TEST_SENATE_USER_PASSWORD"),
        _env("TEST_SENATE_USER_TOTP_SECRET"),
    )


# ------------------------------------------------------------------------------
# HTTP client
# ------------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client() -> httpx.AsyncClient:
    """A shared async HTTP client with a sane timeout."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as ac:
        yield ac


# ------------------------------------------------------------------------------
# Token acquisition
# ------------------------------------------------------------------------------
async def _login(
    client: httpx.AsyncClient, base_url: str, creds: Credentials
) -> str:
    """Log in and return an access token, completing 2FA when configured.

    The auth service enforces mandatory TOTP 2FA. When the account has 2FA
    enabled, ``TEST_*_TOTP_SECRET`` must be set so the harness can generate a
    code. Accounts that still require a password change or 2FA enrollment are
    skipped (they cannot be completed automatically).
    """
    resp = await client.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": creds.username, "password": creds.password},
    )
    resp.raise_for_status()
    body = resp.json()

    if body.get("access_token"):
        return body["access_token"]
    if body.get("must_change_password"):
        pytest.skip("Account requires a password change before login.")
    if body.get("must_setup_2fa"):
        pytest.skip("Account requires 2FA enrollment before login.")
    if body.get("mfa_required"):
        if not creds.totp_secret:
            pytest.skip("2FA required but TEST_*_TOTP_SECRET is not configured.")
        import pyotp

        code = pyotp.TOTP(creds.totp_secret).now()
        verify = await client.post(
            f"{base_url}/api/v1/auth/mfa/verify",
            json={"mfa_token": body["mfa_token"], "code": code},
        )
        verify.raise_for_status()
        return verify.json()["access_token"]
    raise AssertionError(f"Unexpected login response: {body}")


def _mint_token(
    username: str,
    roles: list[str],
    chambers: list[str],
    expires_minutes: int = 60,
) -> Optional[str]:
    """Mint a JWT offline using the shared secret (mirrors mint_test_token.py)."""
    secret = _env("JWT_SECRET_KEY")
    if not secret:
        return None
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "roles": roles,
        "allowed_chambers": chambers,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
        "iss": _env("JWT_ISSUER", "congress-auth"),
        "aud": _env("JWT_AUDIENCE", "congress-platform"),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# Cache tokens per (base_url, username) so the suite logs in at most once per
# account. The auth service rate-limits logins (10 per IP per 300s by default),
# so repeated logins across many tests would otherwise trigger spurious 429s.
_TOKEN_CACHE: Dict[str, str] = {}


async def _token_for(
    client: httpx.AsyncClient,
    base_url: str,
    creds: Credentials,
    *,
    fallback_username: str,
    fallback_roles: list[str],
    fallback_chambers: list[str],
) -> str:
    """Return a token via login, or mint one offline if login creds are absent.

    Tokens are cached per (base_url, username) to avoid exhausting the auth
    service's login rate limit. Skips the calling test when neither a login
    credential pair nor JWT_SECRET_KEY is available.
    """
    if creds.configured:
        cache_key = f"{base_url}|{creds.username}"
        if cache_key not in _TOKEN_CACHE:
            _TOKEN_CACHE[cache_key] = await _login(client, base_url, creds)
        return _TOKEN_CACHE[cache_key]
    minted = _mint_token(fallback_username, fallback_roles, fallback_chambers)
    if minted:
        return minted
    pytest.skip(
        "No credentials configured. Set the relevant TEST_*_USERNAME/PASSWORD "
        "pair (or JWT_SECRET_KEY for offline minting) in tests/.env.test."
    )


@pytest_asyncio.fixture
async def admin_token(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_credentials: Credentials
) -> str:
    return await _token_for(
        client,
        base_urls.auth,
        admin_credentials,
        fallback_username="test_admin",
        fallback_roles=["admin"],
        fallback_chambers=["House", "Senate"],
    )


@pytest_asyncio.fixture
async def user_token(
    client: httpx.AsyncClient, base_urls: BaseURLs, user_credentials: Credentials
) -> str:
    return await _token_for(
        client,
        base_urls.auth,
        user_credentials,
        fallback_username="test_user",
        fallback_roles=["user"],
        fallback_chambers=["House", "Senate"],
    )


@pytest_asyncio.fixture
async def house_token(
    client: httpx.AsyncClient, base_urls: BaseURLs, house_credentials: Credentials
) -> str:
    return await _token_for(
        client,
        base_urls.auth,
        house_credentials,
        fallback_username="test_house_user",
        fallback_roles=["user"],
        fallback_chambers=["House"],
    )


@pytest_asyncio.fixture
async def senate_token(
    client: httpx.AsyncClient, base_urls: BaseURLs, senate_credentials: Credentials
) -> str:
    return await _token_for(
        client,
        base_urls.auth,
        senate_credentials,
        fallback_username="test_senate_user",
        fallback_roles=["user"],
        fallback_chambers=["Senate"],
    )


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def auth_header(token: str) -> Dict[str, str]:
    """Build a Bearer authorization header."""
    return {"Authorization": f"Bearer {token}"}


TERMINAL_STATUSES = {"COMPLETED", "FAILED"}


async def poll_job(
    client: httpx.AsyncClient,
    status_url: str,
    token: str,
    *,
    timeout: int = 120,
    interval: int = 2,
) -> Dict[str, Any]:
    """Poll a job status endpoint until it reaches a terminal state.

    Returns the final status payload. Raises ``TimeoutError`` if the job does
    not finish within ``timeout`` seconds.
    """
    deadline = time.monotonic() + timeout
    last: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        resp = await client.get(status_url, headers=auth_header(token))
        resp.raise_for_status()
        last = resp.json()
        if last.get("status") in TERMINAL_STATUSES:
            return last
        await asyncio.sleep(interval)
    raise TimeoutError(
        f"Job at {status_url} did not reach a terminal state within {timeout}s "
        f"(last status={last.get('status')!r})."
    )


@pytest.fixture
def poll_job_helper():
    """Expose the poll_job coroutine as a fixture for convenience."""
    return poll_job
