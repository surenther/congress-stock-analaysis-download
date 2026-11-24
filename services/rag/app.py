#!/usr/bin/env python3
"""
RAG & Query Retrieval Microservice API.

Provides chamber-scoped retrieval and RAG synthesis over the
``disclosure_embeddings`` table in ``congress-db``. Enforces strict
Chamber-Based Access Control (CBAC): a caller may only query/retrieve
disclosures for the chambers in their ``allowed_chambers`` grant. Unauthorized
cross-chamber requests are rejected with ``403 Forbidden`` BEFORE any embedding
generation or LiteLLM call.

Endpoints
---------
* ``GET  /health``                       — container health probe.
* ``POST /api/v1/rag/query``             — RAG synthesis (embeddings + SQL +
  LiteLLM chat).
* ``POST /api/v1/rag/search-structured`` — raw structured search (no LLM).

All data endpoints require the ``admin`` or ``user`` role.
"""

import csv
import io
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pgvector.asyncpg import register_vector
from pydantic import BaseModel, Field

import auth_utils
import dashboard
import guardrails
import rag_engine
import retriever

# ==============================================================================
# LOGGING
# ==============================================================================
# A dedicated "rag" logger with its own handler so our INFO/DEBUG lines always
# appear in `docker logs` regardless of uvicorn's logging configuration.
logger = logging.getLogger("rag")
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
    """Create the asyncpg pool and register the pgvector codec."""
    global pool
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        init=register_vector,
    )
    # Register the pool for DB-backed authorization checks.
    auth_utils.set_pool(pool)
    # Ensure the value_range_mid SQL helper exists for dashboard aggregation.
    await dashboard.ensure_functions(pool)
    # Personalization: per-user watchlists.
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_watchlists (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(255) NOT NULL,
                type VARCHAR(16) NOT NULL,
                value VARCHAR(255) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (user_id, type, value)
            );
            """
        )
    logger.info("RAG service started; database pool ready.")
    yield
    await pool.close()
    logger.info("RAG service shutting down; database pool closed.")


OPENAPI_TAGS = [
    {
        "name": "General",
        "description": "Health and liveness endpoints.",
    },
    {
        "name": "RAG",
        "description": (
            "Chamber-scoped retrieval and RAG synthesis. Every endpoint requires "
            "a valid JWT (`Authorization: Bearer <token>`) carrying the `admin` "
            "or `user` role. Chamber access is enforced by Chamber-Based Access "
            "Control (CBAC): `user` tokens are limited to their signed "
            "`allowed_chambers` claim, while `admin` tokens always have both "
            "chambers."
        ),
    },
]

app = FastAPI(
    title="Congressional RAG & Query Retrieval Service",
    description=(
        "Chamber-scoped hybrid search and RAG synthesis over congressional "
        "financial disclosures.\n\n"
        "## Authentication\n\n"
        "1. Obtain a JWT from the Auth Service: "
        "`POST http://localhost:8512/api/v1/auth/login` with "
        "`{\"username\": \"...\", \"password\": \"...\"}`.\n"
        "2. Click **Authorize** (top-right) and paste the token, or send "
        "`Authorization: Bearer <token>` on each request.\n"
        "3. The token's `allowed_chambers` claim determines which chambers you "
        "may query.\n\n"
        "## Chamber-Based Access Control (CBAC)\n\n"
        "- `admin` tokens always have `[\"House\", \"Senate\"]`.\n"
        "- `user` tokens are limited to their signed `allowed_chambers` claim "
        "(for example `[\"House\"]`).\n"
        "- A request for an out-of-scope chamber returns **403** with "
        "`{\"detail\": \"Access Denied: You are not authorized to query this "
        "chamber.\"}` **before** any embedding or LLM call is made.\n\n"
        "### How to authenticate a user for a particular chamber\n\n"
        "1. Provision the account with the desired `allowed_chambers` value "
        "(see the Auth Service README, *Provisioning Users Directly in "
        "PostgreSQL*), e.g. `'[\"House\"]'::jsonb`.\n"
        "2. Log in to receive a JWT whose `allowed_chambers` claim matches the "
        "provisioned value.\n"
        "3. Call `GET /api/v1/auth/me` to confirm the grant, then use the token "
        "here. Requests for the other chamber will be rejected with `403`.\n\n"
        "For offline guardrail testing, mint a short-lived token with "
        "`scripts/mint_test_token.py --roles user --allowed-chambers House`."
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
# REQUEST / RESPONSE MODELS
# ==============================================================================

class QueryFilters(BaseModel):
    """Optional metadata filters applied to the scoped search."""

    ticker: Optional[str] = Field(default=None, description="Ticker symbol filter.")
    chamber: Optional[str] = Field(
        default=None, description="Chamber filter ('House' or 'Senate')."
    )
    is_market_trade: Optional[bool] = Field(
        default=None, description="Restrict to market trades when true."
    )
    start_date: Optional[str] = Field(
        default=None, description="Inclusive start date (YYYY-MM-DD)."
    )
    end_date: Optional[str] = Field(
        default=None, description="Inclusive end date (YYYY-MM-DD)."
    )


class RagQueryRequest(BaseModel):
    """Payload for the RAG synthesis endpoint."""

    prompt: str = Field(..., min_length=1, description="Natural-language question.")
    top_k: int = Field(default=10, ge=1, le=50, description="Number of contexts.")
    model: Optional[str] = Field(
        default=None, description="LiteLLM chat model alias override."
    )
    filters: Optional[QueryFilters] = Field(default=None)


class StructuredSearchRequest(BaseModel):
    """Payload for the structured (no-LLM) search endpoint."""

    top_k: int = Field(default=50, ge=1, le=200, description="Maximum rows.")
    filters: Optional[QueryFilters] = Field(default=None)


class SourceCitation(BaseModel):
    doc_id: Optional[str] = None
    document_id: Optional[str] = None
    filer_name: Optional[str] = None
    chamber: Optional[str] = None
    filing_date: Optional[str] = None
    ticker: Optional[str] = None
    asset_name: Optional[str] = None
    action: Optional[str] = None
    date: Optional[str] = None
    value_range: Optional[str] = None
    similarity_score: Optional[float] = None


class UsageInfo(BaseModel):
    """Token usage reported by the synthesis LLM (LiteLLM ``usage`` object)."""

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class RagQueryResponse(BaseModel):
    query: str
    answer: str
    user_chamber_access: List[str]
    sources: List[SourceCitation]
    cost: float = Field(
        default=0.0,
        description="Total request cost in USD (query embedding + synthesis).",
    )
    usage: UsageInfo = Field(
        default_factory=UsageInfo,
        description="Token usage from the synthesis LLM.",
    )


class StructuredSearchResponse(BaseModel):
    user_chamber_access: List[str]
    count: int
    results: List[Dict[str, Any]]


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@app.get("/health", tags=["General"])
async def health():
    """Health check endpoint for Docker container probes."""
    return {"status": "healthy"}


@app.post(
    "/api/v1/rag/query",
    response_model=RagQueryResponse,
    tags=["RAG"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
    responses={
        401: {"description": "Missing, invalid, or expired JWT."},
        403: {
            "description": (
                "CBAC guardrail tripped: the requested chamber (via "
                "`filters.chamber` or explicit cross-chamber intent in the "
                "prompt) is outside the caller's `allowed_chambers`."
            )
        },
    },
)
async def rag_query(
    body: RagQueryRequest,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Run a chamber-scoped RAG query end-to-end.

    **Flow:** resolve allowed chambers -> enforce CBAC guardrails (403 before
    any LLM/embedding work) -> generate query embedding -> scoped SQL search ->
    LiteLLM synthesis -> return Markdown answer + citations.

    **Authorization:** requires the `admin` or `user` role. `user` tokens are
    restricted to their signed `allowed_chambers` claim; `admin` tokens always
    have both chambers. A request for an out-of-scope chamber returns `403`
    before any embedding or LLM call is made.
    """
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    filters = body.filters or QueryFilters()

    # Pre-LLM guardrail: reject unauthorized chamber access immediately.
    guardrails.enforce_chamber_guardrails(
        prompt=body.prompt,
        requested_chamber=filters.chamber,
        allowed_chambers=allowed_chambers,
    )

    search = await retriever.hybrid_search(
        pool=pool,
        query=body.prompt,
        allowed_chambers=allowed_chambers,
        top_k=body.top_k,
        ticker=filters.ticker,
        is_market_trade=filters.is_market_trade,
        start_date=filters.start_date,
        end_date=filters.end_date,
    )
    sources = search["results"]

    synthesis = rag_engine.synthesize(
        query=body.prompt,
        sources=sources,
        allowed_chambers=allowed_chambers,
        user_id=payload.get("sub"),
        model=body.model,
    )

    total_cost = search.get("embedding_cost", 0.0) + synthesis.get("cost", 0.0)

    logger.info(
        "RAG query user=%s chambers=%s sources=%d cost=$%.6f",
        payload.get("sub"),
        allowed_chambers,
        len(sources),
        total_cost,
    )

    return {
        "query": body.prompt,
        "answer": synthesis["answer"],
        "user_chamber_access": allowed_chambers,
        "sources": synthesis["sources"],
        "cost": total_cost,
        "usage": synthesis.get("usage") or {},
    }


@app.post(
    "/api/v1/rag/search-structured",
    response_model=StructuredSearchResponse,
    tags=["RAG"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
    responses={
        401: {"description": "Missing, invalid, or expired JWT."},
        403: {
            "description": (
                "CBAC guardrail tripped: `filters.chamber` is outside the "
                "caller's `allowed_chambers`."
            )
        },
    },
)
async def search_structured(
    body: StructuredSearchRequest,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Run a chamber-scoped structured search WITHOUT calling the LLM.

    Enforces the ``allowed_chambers`` SQL filter and returns raw matching rows.

    **Authorization:** requires the `admin` or `user` role. `user` tokens are
    restricted to their signed `allowed_chambers` claim; `admin` tokens always
    have both chambers.
    """
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    filters = body.filters or QueryFilters()

    # Guardrail: an explicit chamber filter must be within the caller's grant.
    guardrails.enforce_chamber_filter(filters.chamber, allowed_chambers)

    results = await retriever.structured_search(
        pool=pool,
        allowed_chambers=allowed_chambers,
        top_k=body.top_k,
        ticker=filters.ticker,
        is_market_trade=filters.is_market_trade,
        start_date=filters.start_date,
        end_date=filters.end_date,
    )

    logger.info(
        "Structured search user=%s chambers=%s rows=%d",
        payload.get("sub"),
        allowed_chambers,
        len(results),
    )

    return {
        "user_chamber_access": allowed_chambers,
        "count": len(results),
        "results": results,
    }


# ==============================================================================
# STREAMING SYNTHESIS
# ==============================================================================

@app.post(
    "/api/v1/rag/query/stream",
    tags=["RAG"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
    responses={
        401: {"description": "Missing, invalid, or expired JWT."},
        403: {"description": "CBAC guardrail tripped (structured 403 body)."},
    },
)
async def rag_query_stream(
    body: RagQueryRequest,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Stream a chamber-scoped RAG answer as Server-Sent Events.

    Emits ``data: {"delta": "..."}`` events and a final ``data: [DONE]``. The
    same CBAC guardrails run before any embedding or LLM call.
    """
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    filters = body.filters or QueryFilters()
    guardrails.enforce_chamber_guardrails(
        prompt=body.prompt,
        requested_chamber=filters.chamber,
        allowed_chambers=allowed_chambers,
    )
    search = await retriever.hybrid_search(
        pool=pool,
        query=body.prompt,
        allowed_chambers=allowed_chambers,
        top_k=body.top_k,
        ticker=filters.ticker,
        is_market_trade=filters.is_market_trade,
        start_date=filters.start_date,
        end_date=filters.end_date,
    )
    sources = search["results"]

    def event_stream():
        try:
            for chunk in rag_engine.synthesize_stream(
                query=body.prompt,
                sources=sources,
                allowed_chambers=allowed_chambers,
                user_id=payload.get("sub"),
                model=body.model,
            ):
                yield chunk
        except Exception as exc:  # pragma: no cover - network dependent
            logger.error("RAG stream failed: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ==============================================================================
# EXPORT
# ==============================================================================

class RagExportRequest(BaseModel):
    """Payload for the RAG export endpoint."""

    format: str = Field(default="csv", description="'csv' or 'pdf'.")
    top_k: int = Field(default=200, ge=1, le=1000)
    filters: Optional[QueryFilters] = Field(default=None)


_RAG_EXPORT_COLUMNS = [
    "doc_id", "chamber", "filer_name", "filing_date", "ticker",
    "asset_name", "action", "date", "value_range", "ownership",
]


def _render_rag_pdf(rows: List[Dict[str, Any]], scope: List[str]) -> bytes:
    """Render a simple PDF of the structured search results."""
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
        Paragraph("Congressional Disclosure RAG Export", styles["Title"]),
        Paragraph(
            f"Scope: {', '.join(scope)} &middot; Rows: {len(rows)} &middot; "
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]
    header = ["Filer", "Chamber", "Filed", "Ticker", "Action", "Value"]
    data = [header]
    for row in rows[:500]:
        data.append([
            str(row.get("filer_name") or ""),
            str(row.get("chamber") or ""),
            str(row.get("filing_date") or ""),
            str(row.get("ticker") or ""),
            str(row.get("action") or ""),
            str(row.get("value_range") or ""),
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


@app.post(
    "/api/v1/rag/export",
    tags=["RAG"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
    responses={
        401: {"description": "Missing, invalid, or expired JWT."},
        403: {"description": "CBAC guardrail tripped (structured 403 body)."},
    },
)
async def rag_export(
    body: RagExportRequest,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Export chamber-scoped structured search results as CSV or PDF."""
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    filters = body.filters or QueryFilters()
    guardrails.enforce_chamber_filter(filters.chamber, allowed_chambers)

    results = await retriever.structured_search(
        pool=pool,
        allowed_chambers=allowed_chambers,
        top_k=body.top_k,
        ticker=filters.ticker,
        is_market_trade=filters.is_market_trade,
        start_date=filters.start_date,
        end_date=filters.end_date,
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    if body.format == "pdf":
        return Response(
            content=_render_rag_pdf(results, allowed_chambers),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="rag-export-{stamp}.pdf"'
            },
        )

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=_RAG_EXPORT_COLUMNS, extrasaction="ignore"
    )
    writer.writeheader()
    for row in results:
        writer.writerow({k: row.get(k) for k in _RAG_EXPORT_COLUMNS})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="rag-export-{stamp}.csv"'
        },
    )


# ==============================================================================
# LLM-DRIVEN DASHBOARD
# ==============================================================================

class DashboardAnalyticsRequest(BaseModel):
    """Payload for the LLM-driven dashboard spec endpoint."""

    chamber: Optional[str] = Field(
        default=None, description="'House', 'Senate', or 'Combined'."
    )
    horizon: Optional[str] = Field(
        default="90 Days",
        description="30 Days, 90 Days, YTD, 1 Year, or All Time.",
    )
    time_horizon: Optional[str] = Field(default=None, description="Alias for horizon.")
    model: Optional[str] = Field(default=None, description="LiteLLM model override.")


@app.post(
    "/api/v1/rag/dashboard/analytics",
    tags=["RAG"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
    responses={
        401: {"description": "Missing, invalid, or expired JWT."},
        403: {"description": "CBAC guardrail tripped (structured 403 body)."},
        502: {"description": "The LLM could not produce a dashboard spec."},
        503: {"description": "No disclosure data available yet."},
    },
)
async def dashboard_analytics(
    body: DashboardAnalyticsRequest,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Generate a schema-driven dashboard spec from real data via the LLM.

    The numeric series and table rows always come from the database; the LLM
    authors the presentation copy. No hardcoded or dummy values are returned.
    """
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    requested = body.chamber
    if requested and requested not in ("Combined", "All"):
        guardrails.enforce_chamber_filter(requested, allowed_chambers)
        scope_chambers = [requested]
    else:
        scope_chambers = allowed_chambers

    horizon = body.time_horizon or body.horizon

    async with pool.acquire() as conn:
        has_data = await conn.fetchval(
            "SELECT to_regclass('public.disclosure_embeddings') IS NOT NULL"
        )
        if not has_data:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "No disclosure data is available yet. Run the ingestion "
                    "pipeline (download -> parse -> vectorize) first."
                ),
            )
        data = await dashboard.gather(conn, scope_chambers, horizon)

    try:
        spec = dashboard.synthesize_spec(
            data, allowed_chambers, horizon, model=body.model
        )
    except RuntimeError as exc:
        logger.error("Dashboard LLM synthesis failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dashboard synthesis failed: {exc}",
        )
    return spec


# ==============================================================================
# WATCHLISTS (personalization)
# ==============================================================================

class WatchlistCreate(BaseModel):
    """Payload for adding a watchlist entry."""

    type: str = Field(..., description="'member' or 'ticker'.")
    value: str = Field(..., min_length=1, max_length=255)


@app.get(
    "/api/v1/watchlists",
    tags=["Watchlists"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def list_watchlists(
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """List the caller's watchlist entries."""
    username = payload.get("sub")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, type, value, created_at FROM user_watchlists "
            "WHERE user_id = $1 ORDER BY created_at DESC",
            username,
        )
    return {
        "items": [
            {
                "id": str(r["id"]),
                "type": r["type"],
                "value": r["value"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]
    }


@app.post(
    "/api/v1/watchlists",
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="type must be 'member' or 'ticker'.",
        )
    value = body.value.strip()
    if body.type == "ticker":
        value = value.upper()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO user_watchlists (user_id, type, value)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, type, value) DO UPDATE SET value = EXCLUDED.value
            RETURNING id, type, value, created_at
            """,
            payload.get("sub"),
            body.type,
            value,
        )
    return {
        "id": str(row["id"]),
        "type": row["type"],
        "value": row["value"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
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
        result = await conn.execute(
            "DELETE FROM user_watchlists WHERE id = $1::uuid AND user_id = $2",
            watchlist_id,
            payload.get("sub"),
        )
    if result.endswith("0"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watchlist entry not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/api/v1/watchlists/feed",
    tags=["Watchlists"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def watchlist_feed(
    limit: int = 50,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Recent disclosures matching the caller's watched members or tickers."""
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    username = payload.get("sub")
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT type, value FROM user_watchlists WHERE user_id = $1", username
        )
        members = [r["value"].lower() for r in rows if r["type"] == "member"]
        tickers = [r["value"].upper() for r in rows if r["type"] == "ticker"]
        if not members and not tickers:
            return {"scope": allowed_chambers, "count": 0, "results": []}
        fetched = await conn.fetch(
            """
            SELECT doc_id, filer_name, chamber, filing_date,
                   date AS transaction_date, ticker, asset_name, action, value_range
            FROM disclosure_embeddings
            WHERE is_market_trade = TRUE
              AND chamber = ANY($1::text[])
              AND (LOWER(filer_name) = ANY($2::text[]) OR UPPER(ticker) = ANY($3::text[]))
            ORDER BY filing_date DESC NULLS LAST
            LIMIT $4
            """,
            allowed_chambers,
            members,
            tickers,
            limit,
        )
    return {
        "scope": allowed_chambers,
        "count": len(fetched),
        "results": [retriever._row_to_dict(r) for r in fetched],
    }
