#!/usr/bin/env python3
"""
Tests for the analytics-service (port 8517).

Covers: health, scope resolution, the schema-driven dashboard, the analytics
endpoints, CSV/PDF export, watchlist CRUD, and chamber-scope enforcement.
"""

from __future__ import annotations

import httpx
import pytest

from conftest import BaseURLs, auth_header

pytestmark = pytest.mark.contract


async def test_health(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.analytics}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "healthy"}


async def test_scope_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.analytics}/api/v1/analytics/scope")
    assert resp.status_code == 401


async def test_dashboard_requires_auth(client: httpx.AsyncClient, base_urls: BaseURLs):
    resp = await client.get(f"{base_urls.analytics}/api/v1/analytics/dashboard")
    assert resp.status_code == 401


async def test_scope_with_admin(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/scope",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["allowed_chambers"]) == {"House", "Senate"}


async def test_dashboard_layout(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/dashboard",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["widgets"], list) and body["widgets"]
    types = {w["type"] for w in body["widgets"]}
    assert {"top_assets", "volume_trends", "late_filings", "committee_sector"} <= types


async def test_top_assets(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/top-assets",
        headers=auth_header(admin_token),
        params={"limit": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body and isinstance(body["results"], list)


async def test_volume_trends(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/volume-trends",
        headers=auth_header(admin_token),
        params={"granularity": "month"},
    )
    assert resp.status_code == 200
    assert resp.json()["granularity"] == "month"


async def test_volume_trends_rejects_bad_granularity(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/volume-trends",
        headers=auth_header(admin_token),
        params={"granularity": "week"},
    )
    assert resp.status_code == 422


async def test_late_filings(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/late-filings",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body and "results" in body


async def test_committee_sector(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/committee-sector",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["results"], list)


async def test_disclosures_grid(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/disclosures",
        headers=auth_header(admin_token),
        params={"limit": 5, "sort": "filing_date", "order": "desc"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body and "results" in body


async def test_export_csv(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/export",
        headers=auth_header(admin_token),
        params={"format": "csv", "limit": 5},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


async def test_export_pdf(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/export",
        headers=auth_header(admin_token),
        params={"format": "pdf", "limit": 5},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


async def test_scope_enforcement_house_user(
    client: httpx.AsyncClient, base_urls: BaseURLs, house_token: str
):
    """A House-only user requesting Senate data gets a structured 403."""
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/analytics/top-assets",
        headers=auth_header(house_token),
        params={"chamber": "Senate"},
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["code"] == "CHAMBER_SCOPE_VIOLATION"
    assert detail["requested_chamber"] == "Senate"
    assert "House" in detail["allowed_chambers"]


async def test_watchlist_crud(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    headers = auth_header(admin_token)
    # Add
    resp = await client.post(
        f"{base_urls.analytics}/api/v1/watchlists",
        headers=headers,
        json={"type": "ticker", "value": "nvda"},
    )
    assert resp.status_code == 201
    item = resp.json()
    assert item["value"] == "NVDA"
    # List
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/watchlists", headers=headers
    )
    assert resp.status_code == 200
    assert any(i["id"] == item["id"] for i in resp.json()["items"])
    # Delete
    resp = await client.delete(
        f"{base_urls.analytics}/api/v1/watchlists/{item['id']}", headers=headers
    )
    assert resp.status_code == 204


async def test_watchlist_invalid_type(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.post(
        f"{base_urls.analytics}/api/v1/watchlists",
        headers=auth_header(admin_token),
        json={"type": "sector", "value": "Tech"},
    )
    assert resp.status_code == 422


async def test_watchlist_feed(
    client: httpx.AsyncClient, base_urls: BaseURLs, admin_token: str
):
    resp = await client.get(
        f"{base_urls.analytics}/api/v1/watchlists/feed",
        headers=auth_header(admin_token),
    )
    assert resp.status_code == 200
    assert "results" in resp.json()
