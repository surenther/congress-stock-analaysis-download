#!/usr/bin/env python3
"""
Analytics Microservice API.

Chamber-scoped, read-only analytics over the congressional disclosure dataset.
Serves the schema-driven dashboard, top traded assets, volume trends, late
filings, committee/sector correlation, the interactive data grid, exports, and
per-user watchlists.

All data endpoints require the ``admin`` or ``user`` role and enforce
Chamber-Based Access Control (CBAC): a ``user`` may only read the chambers in
their signed ``allowed_chambers`` claim, while ``admin`` always has both.
"""

import csv
import io
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import Response
from pydantic import BaseModel, Field

import auth_utils
import db_init
import queries
import scope_errors

# ==============================================================================
# LOGGING
# ==============================================================================
logger = logging.getLogger("analytics")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL must be set (e.g. "
        "postgresql://user:password@db:5432/congress_db)."
    )

pool: Optional[asyncpg.Pool] = None


# ==============================================================================
# LIFESPAN
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the asyncpg pool and ensure the analytics schema exists."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    auth_utils.set_pool(pool)
    await db_init.init_db(pool)
    logger.info("Analytics service started; database pool ready.")
    yield
    await pool.close()
    logger.info("Analytics service shutting down; database pool closed.")


OPENAPI_TAGS = [
    {"name": "General", "description": "Health and scope endpoints."},
    {
        "name": "Analytics",
        "description": (
            "Chamber-scoped analytics. Every endpoint requires a valid JWT "
            "(`Authorization: Bearer <token>`) carrying the `admin` or `user` "
            "role. Chamber access is enforced by Chamber-Based Access Control "
            "(CBAC)."
        ),
    },
    {"name": "Watchlists", "description": "Per-user member and ticker watchlists."},
]

app = FastAPI(
    title="Congressional Disclosure Analytics Service",
    description=(
        "Chamber-scoped analytics over congressional financial disclosures.\n\n"
        "## Authentication\n\n"
        "Obtain a JWT from the Auth Service "
        "(`POST http://localhost:8512/api/v1/auth/login`) and send it as "
        "`Authorization: Bearer <token>`.\n\n"
        "## Chamber-Based Access Control (CBAC)\n\n"
        "- `admin` tokens always have `[\"House\", \"Senate\"]`.\n"
        "- `user` tokens are limited to their signed `allowed_chambers` claim.\n"
        "- Out-of-scope chamber requests return **403** before any query runs."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)


def custom_openapi():
    """Inject the HTTP bearer security scheme so Swagger UI shows Authorize."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=OPENAPI_TAGS,
    )
    components = schema.setdefault("components", {})
    components.setdefault("securitySchemes", {})["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "JWT issued by the Auth Service. Paste the `access_token` value "
            "from `POST /api/v1/auth/login`."
        ),
    }
    schema["security"] = [{"bearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


# ==============================================================================
# SECURITY HEADERS
# ==============================================================================

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach baseline security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
    return response


# ==============================================================================
# MODELS
# ==============================================================================

class ScopeResponse(BaseModel):
    username: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    allowed_chambers: List[str] = Field(default_factory=list)


class WidgetDescriptor(BaseModel):
    id: str
    type: str
    title: str
    description: Optional[str] = None
    span: int = Field(default=1, description="Grid column span (1-2).")
    config: Dict[str, Any] = Field(default_factory=dict)


class DashboardResponse(BaseModel):
    scope: List[str]
    generated_at: str
    widgets: List[WidgetDescriptor]


class TopAssetsResponse(BaseModel):
    scope: List[str]
    count: int
    results: List[Dict[str, Any]]


class VolumeTrendsResponse(BaseModel):
    scope: List[str]
    granularity: str
    results: List[Dict[str, Any]]


class LateFilingsResponse(BaseModel):
    scope: List[str]
    total: int
    limit: int
    offset: int
    results: List[Dict[str, Any]]


class CommitteeSectorResponse(BaseModel):
    scope: List[str]
    results: List[Dict[str, Any]]


class DisclosuresResponse(BaseModel):
    scope: List[str]
    total: int
    limit: int
    offset: int
    results: List[Dict[str, Any]]


class WatchlistCreate(BaseModel):
    type: str = Field(..., description="'member' or 'ticker'.")
    value: str = Field(..., min_length=1, max_length=255)


class WatchlistItem(BaseModel):
    id: str
    type: str
    value: str
    created_at: Optional[str] = None


class WatchlistListResponse(BaseModel):
    items: List[WatchlistItem]


class WatchlistFeedResponse(BaseModel):
    scope: List[str]
    count: int
    results: List[Dict[str, Any]]


# ==============================================================================
# HELPERS
# ==============================================================================

def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value else None


async def _scope(payload: Dict[str, Any]) -> List[str]:
    return await auth_utils.get_allowed_chambers(payload)


def _enforce_chamber(requested: Optional[str], allowed: List[str]) -> None:
    """Reject an explicit chamber filter outside the caller's grant."""
    if requested is None:
        return
    canonical = None
    for chamber in queries.ALL_CHAMBERS:
        if requested.strip().lower() == chamber.lower():
            canonical = chamber
            break
    if canonical is None or canonical not in allowed:
        raise scope_errors.chamber_scope_violation(requested, allowed)


async def _user_id(conn, username: str) -> Optional[str]:
    row = await conn.fetchval(
        "SELECT id FROM users WHERE username = $1", username
    )
    return str(row) if row else None


# ==============================================================================
# GENERAL
# ==============================================================================

@app.get("/health", tags=["General"])
async def health():
    """Health check endpoint for Docker container probes."""
    return {"status": "healthy"}


@app.get(
    "/api/v1/analytics/scope",
    response_model=ScopeResponse,
    tags=["General"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def scope(payload: Dict[str, Any] = Depends(auth_utils.verify_token)):
    """Return the caller's resolved roles and chamber scope."""
    allowed = await _scope(payload)
    return {
        "username": payload.get("sub"),
        "roles": auth_utils._coerce_list(payload.get("roles", [])),
        "allowed_chambers": allowed,
    }


@app.get(
    "/api/v1/analytics/dashboard",
    response_model=DashboardResponse,
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def dashboard(payload: Dict[str, Any] = Depends(auth_utils.verify_token)):
    """Return the schema-driven dashboard layout for the caller's scope."""
    allowed = await _scope(payload)
    widgets = [
        WidgetDescriptor(
            id="top-assets",
            type="top_assets",
            title="Top Traded Assets",
            description="Most purchased and sold assets in scope.",
            span=2,
            config={"endpoint": "/api/v1/analytics/top-assets"},
        ),
        WidgetDescriptor(
            id="volume-trends",
            type="volume_trends",
            title="Trading Volume Trends",
            description="Monthly purchase and sale volume.",
            span=2,
            config={"endpoint": "/api/v1/analytics/volume-trends"},
        ),
        WidgetDescriptor(
            id="late-filings",
            type="late_filings",
            title="Late Filing & STOCK Act Compliance",
            description="Disclosures filed beyond the 45-day window.",
            span=1,
            config={"endpoint": "/api/v1/analytics/late-filings"},
        ),
        WidgetDescriptor(
            id="committee-sector",
            type="committee_sector",
            title="Committee & Sector Correlation",
            description="Member committee assignments vs traded sectors.",
            span=1,
            config={"endpoint": "/api/v1/analytics/committee-sector"},
        ),
    ]
    return {
        "scope": allowed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "widgets": widgets,
    }


# ==============================================================================
# ANALYTICS
# ==============================================================================

@app.get(
    "/api/v1/analytics/top-assets",
    response_model=TopAssetsResponse,
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def top_assets(
    chamber: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None, description="Purchase or Sale."),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Top purchased/sold assets within the caller's chamber scope."""
    allowed = await _scope(payload)
    _enforce_chamber(chamber, allowed)
    scope_chambers = [chamber] if chamber else allowed
    async with pool.acquire() as conn:
        table = await queries.resolve_facts_table(conn)
        if not table:
            return {"scope": allowed, "count": 0, "results": []}
        sql, params = queries.top_assets_sql(
            table, scope_chambers, action, start_date, end_date, limit
        )
        rows = await conn.fetch(sql, *params)
    return {
        "scope": allowed,
        "count": len(rows),
        "results": [dict(row) for row in rows],
    }


@app.get(
    "/api/v1/analytics/volume-trends",
    response_model=VolumeTrendsResponse,
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def volume_trends(
    chamber: Optional[str] = Query(default=None),
    granularity: str = Query(default="month", pattern="^(month|quarter)$"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Trading volume time series grouped by month or quarter."""
    allowed = await _scope(payload)
    _enforce_chamber(chamber, allowed)
    scope_chambers = [chamber] if chamber else allowed
    async with pool.acquire() as conn:
        table = await queries.resolve_facts_table(conn)
        if not table:
            return {"scope": allowed, "granularity": granularity, "results": []}
        sql, params = queries.volume_trends_sql(
            table, scope_chambers, granularity, start_date, end_date
        )
        rows = await conn.fetch(sql, *params)
    return {
        "scope": allowed,
        "granularity": granularity,
        "results": [dict(row) for row in rows],
    }


@app.get(
    "/api/v1/analytics/late-filings",
    response_model=LateFilingsResponse,
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def late_filings(
    chamber: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Disclosures filed beyond the mandatory 45-day STOCK Act window."""
    allowed = await _scope(payload)
    _enforce_chamber(chamber, allowed)
    scope_chambers = [chamber] if chamber else allowed
    async with pool.acquire() as conn:
        table = await queries.resolve_facts_table(conn)
        if not table:
            return {
                "scope": allowed, "total": 0, "limit": limit,
                "offset": offset, "results": [],
            }
        count_sql, count_params = queries.late_filings_count_sql(
            table, scope_chambers
        )
        total = await conn.fetchval(count_sql, *count_params)
        sql, params = queries.late_filings_sql(
            table, scope_chambers, limit, offset
        )
        rows = await conn.fetch(sql, *params)
    return {
        "scope": allowed,
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "results": [dict(row) for row in rows],
    }


@app.get(
    "/api/v1/analytics/committee-sector",
    response_model=CommitteeSectorResponse,
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def committee_sector(
    chamber: Optional[str] = Query(default=None),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Correlate member committee assignments with traded market sectors."""
    allowed = await _scope(payload)
    _enforce_chamber(chamber, allowed)
    scope_chambers = [chamber] if chamber else allowed
    async with pool.acquire() as conn:
        table = await queries.resolve_facts_table(conn)
        if not table:
            return {"scope": allowed, "results": []}
        sql, params = queries.committee_sector_sql(table, scope_chambers)
        rows = await conn.fetch(sql, *params)
    return {"scope": allowed, "results": [dict(row) for row in rows]}


@app.get(
    "/api/v1/analytics/disclosures",
    response_model=DisclosuresResponse,
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def disclosures(
    chamber: Optional[str] = Query(default=None),
    ticker: Optional[str] = Query(default=None),
    member: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    min_value: Optional[float] = Query(default=None, ge=0),
    max_value: Optional[float] = Query(default=None, ge=0),
    sort: str = Query(default="filing_date"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Filtered, sorted, paginated disclosure data grid."""
    allowed = await _scope(payload)
    _enforce_chamber(chamber, allowed)
    scope_chambers = [chamber] if chamber else allowed
    async with pool.acquire() as conn:
        table = await queries.resolve_facts_table(conn)
        if not table:
            return {
                "scope": allowed, "total": 0, "limit": limit,
                "offset": offset, "results": [],
            }
        count_sql, count_params = queries.disclosures_count_sql(
            table, scope_chambers, ticker, member, action,
            start_date, end_date, min_value, max_value,
        )
        total = await conn.fetchval(count_sql, *count_params)
        sql, params = queries.disclosures_sql(
            table, scope_chambers, ticker, member, action,
            start_date, end_date, min_value, max_value,
            sort, order, limit, offset,
        )
        rows = await conn.fetch(sql, *params)
    return {
        "scope": allowed,
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "results": [dict(row) for row in rows],
    }


# ==============================================================================
# EXPORT
# ==============================================================================

_EXPORT_COLUMNS = [
    "doc_id", "filer_name", "chamber", "party", "state", "filing_date",
    "transaction_date", "days_to_file", "ticker", "asset_name",
    "asset_category", "action", "value_range", "ownership", "sector",
]


@app.get(
    "/api/v1/analytics/export",
    tags=["Analytics"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def export(
    format: str = Query(default="csv", pattern="^(csv|pdf)$"),
    chamber: Optional[str] = Query(default=None),
    ticker: Optional[str] = Query(default=None),
    member: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    min_value: Optional[float] = Query(default=None, ge=0),
    max_value: Optional[float] = Query(default=None, ge=0),
    limit: int = Query(default=1000, ge=1, le=10000),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Export the filtered disclosure grid as CSV or a PDF summary."""
    allowed = await _scope(payload)
    _enforce_chamber(chamber, allowed)
    scope_chambers = [chamber] if chamber else allowed
    async with pool.acquire() as conn:
        table = await queries.resolve_facts_table(conn)
        rows: List[Dict[str, Any]] = []
        if table:
            sql, params = queries.disclosures_sql(
                table, scope_chambers, ticker, member, action,
                start_date, end_date, min_value, max_value,
                "filing_date", "desc", limit, 0,
            )
            fetched = await conn.fetch(sql, *params)
            rows = [dict(r) for r in fetched]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=_EXPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in _EXPORT_COLUMNS})
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="disclosures-{stamp}.csv"'
            },
        )

    pdf_bytes = _render_pdf(rows, allowed)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="disclosures-{stamp}.pdf"'
        },
    )


def _render_pdf(rows: List[Dict[str, Any]], scope: List[str]) -> bytes:
    """Render a simple PDF executive summary of the disclosure rows."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    styles = getSampleStyleSheet()
    elements: List[Any] = [
        Paragraph("Congressional Disclosure Export", styles["Title"]),
        Paragraph(
            f"Scope: {', '.join(scope)} &middot; Rows: {len(rows)} &middot; "
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]

    header = ["Filer", "Chamber", "Filed", "Ticker", "Action", "Value", "Sector"]
    data = [header]
    for row in rows[:500]:
        data.append([
            str(row.get("filer_name") or ""),
            str(row.get("chamber") or ""),
            str(row.get("filing_date") or ""),
            str(row.get("ticker") or ""),
            str(row.get("action") or ""),
            str(row.get("value_range") or ""),
            str(row.get("sector") or ""),
        ])
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ])
    )
    elements.append(table)
    doc.build(elements)
    return buffer.getvalue()


# ==============================================================================
# WATCHLISTS
# ==============================================================================

@app.get(
    "/api/v1/watchlists",
    response_model=WatchlistListResponse,
    tags=["Watchlists"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def list_watchlists(payload: Dict[str, Any] = Depends(auth_utils.verify_token)):
    """List the caller's watchlist entries."""
    async with pool.acquire() as conn:
        user_id = await _user_id(conn, payload.get("sub"))
        if not user_id:
            return {"items": []}
        rows = await conn.fetch(
            "SELECT id, type, value, created_at FROM user_watchlists "
            "WHERE user_id = $1::uuid ORDER BY created_at DESC",
            user_id,
        )
    return {
        "items": [
            {
                "id": str(r["id"]),
                "type": r["type"],
                "value": r["value"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ]
    }


@app.post(
    "/api/v1/watchlists",
    response_model=WatchlistItem,
    status_code=status.HTTP_201_CREATED,
    tags=["Watchlists"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def add_watchlist(
    body: WatchlistCreate,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Add a member or ticker to the caller's watchlist."""
    if body.type not in ("member", "ticker"):
        raise HTTPException(status_code=422, detail="type must be 'member' or 'ticker'.")
    value = body.value.strip()
    if body.type == "ticker":
        value = value.upper()
    async with pool.acquire() as conn:
        user_id = await _user_id(conn, payload.get("sub"))
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
        row = await conn.fetchrow(
            """
            INSERT INTO user_watchlists (user_id, type, value)
            VALUES ($1::uuid, $2, $3)
            ON CONFLICT (user_id, type, value) DO UPDATE SET value = EXCLUDED.value
            RETURNING id, type, value, created_at
            """,
            user_id,
            body.type,
            value,
        )
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "value": row["value"],
        "created_at": _iso(row["created_at"]),
    }


@app.delete(
    "/api/v1/watchlists/{watchlist_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Watchlists"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def delete_watchlist(
    watchlist_id: str,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Remove a watchlist entry owned by the caller."""
    async with pool.acquire() as conn:
        user_id = await _user_id(conn, payload.get("sub"))
        if not user_id:
            raise HTTPException(status_code=404, detail="User not found")
        result = await conn.execute(
            "DELETE FROM user_watchlists WHERE id = $1::uuid AND user_id = $2::uuid",
            watchlist_id,
            user_id,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Watchlist entry not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/api/v1/watchlists/feed",
    response_model=WatchlistFeedResponse,
    tags=["Watchlists"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def watchlist_feed(
    limit: int = Query(default=50, ge=1, le=200),
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Recent disclosures matching the caller's watched members or tickers."""
    allowed = await _scope(payload)
    async with pool.acquire() as conn:
        user_id = await _user_id(conn, payload.get("sub"))
        members: List[str] = []
        tickers: List[str] = []
        if user_id:
            rows = await conn.fetch(
                "SELECT type, value FROM user_watchlists WHERE user_id = $1::uuid",
                user_id,
            )
            for row in rows:
                if row["type"] == "member":
                    members.append(row["value"])
                elif row["type"] == "ticker":
                    tickers.append(row["value"])
        table = await queries.resolve_facts_table(conn)
        if not table or (not members and not tickers):
            return {"scope": allowed, "count": 0, "results": []}
        sql, params = queries.watchlist_feed_sql(
            table, allowed, members, tickers, limit
        )
        fetched = await conn.fetch(sql, *params)
    return {
        "scope": allowed,
        "count": len(fetched),
        "results": [dict(r) for r in fetched],
    }
