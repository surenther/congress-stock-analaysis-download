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
from fastapi import Depends, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pgvector.asyncpg import register_vector
from pydantic import BaseModel, Field

import auth_utils
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


@app.post(
    "/api/v1/rag/dashboard/analytics",
    tags=["RAG", "Dashboard"],
    dependencies=[Depends(auth_utils.require_role(["admin", "user"]))],
)
async def dashboard_analytics(
    body: Dict[str, Any] = None,
    payload: Dict[str, Any] = Depends(auth_utils.verify_token),
):
    """Return schema-driven dashboard layout and visual widget specifications."""
    allowed_chambers = await auth_utils.get_allowed_chambers(payload)
    req_chamber = (body or {}).get("chamber")
    if req_chamber and req_chamber != "Combined":
        guardrails.enforce_chamber_filter(req_chamber, allowed_chambers)

    chamber = req_chamber or ("Combined" if len(allowed_chambers) > 1 else allowed_chambers[0])
    is_house = chamber == "House"
    is_senate = chamber == "Senate"
    total_volume = 284500000 if is_house else 193200000 if is_senate else 477700000
    active_members = 142 if is_house else 54 if is_senate else 196
    buy_sell_ratio = 1.45 if is_house else 0.88 if is_senate else 1.22
    late_filings = 23 if is_house else 14 if is_senate else 37

    return {
        "status": "success",
        "chamber_scope": allowed_chambers,
        "time_horizon": (body or {}).get("timeHorizon", "90 Days"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "total_volume": total_volume,
            "active_members": active_members,
            "buy_sell_ratio": buy_sell_ratio,
            "late_filings_count": late_filings,
        },
        "widgets": [
            {
                "id": "kpi-volume",
                "widget_type": "metric_card",
                "title": "Total Traded Volume",
                "span": 1,
                "data": {
                    "category": "Trading Volume",
                    "value": f"${total_volume/1_000_000:.1f}M",
                    "trend_percentage": 14.2,
                    "trend_direction": "up",
                    "trend_label": "+14.2% vs previous period",
                },
            },
            {
                "id": "kpi-members",
                "widget_type": "metric_card",
                "title": "Active Trading Members",
                "span": 1,
                "data": {
                    "category": "Congressional Filers",
                    "value": active_members,
                    "trend_percentage": -2.8,
                    "trend_direction": "down",
                    "trend_label": "-2.8% active traders",
                },
            },
            {
                "id": "kpi-ratio",
                "widget_type": "metric_card",
                "title": "Buy vs Sell Volume Ratio",
                "span": 1,
                "data": {
                    "category": "Sentiment Index",
                    "value": f"{buy_sell_ratio:.2f}x",
                    "trend_percentage": 8.5,
                    "trend_direction": "up",
                    "trend_label": "Bullish Congressional Net-Buy" if buy_sell_ratio > 1 else "Bearish Net-Sell",
                },
            },
            {
                "id": "kpi-late",
                "widget_type": "metric_card",
                "title": "STOCK Act Late Filings",
                "span": 1,
                "data": {
                    "category": "Compliance Watch",
                    "value": late_filings,
                    "trend_percentage": -12.4,
                    "trend_direction": "up",
                    "trend_label": "Disclosed >45 days late",
                },
            },
            {
                "id": "chart-monthly-volume",
                "widget_type": "bar_chart",
                "title": "Monthly Trading Volume & Sentiment",
                "description": "Stacked disclosure values comparing purchases vs sales (in USD)",
                "span": 2,
                "data": {
                    "xAxisKey": "month",
                    "series": [
                        {"dataKey": "purchases", "name": "Purchases", "color": "#10b981", "stackId": "a"},
                        {"dataKey": "sales", "name": "Sales", "color": "#f43f5e", "stackId": "a"},
                    ],
                    "items": [
                        {"month": "2026-05", "purchases": 14200000, "sales": 8900000},
                        {"month": "2026-06", "purchases": 19800000, "sales": 12400000},
                        {"month": "2026-07", "purchases": 24500000, "sales": 18200000},
                        {"month": "2026-08", "purchases": 16700000, "sales": 14100000},
                        {"month": "2026-09", "purchases": 29400000, "sales": 21300000},
                        {"month": "2026-10", "purchases": 38200000, "sales": 25400000},
                        {"month": "2026-11", "purchases": 31500000, "sales": 19800000},
                    ],
                },
            },
            {
                "id": "chart-volume-timeline",
                "widget_type": "line_chart",
                "title": "Trading Momentum & Intensity",
                "description": "Aggregate transaction velocity timeline",
                "span": 2,
                "data": {
                    "xAxisKey": "period",
                    "series": [
                        {"dataKey": "total_flow", "name": "Total Capital Flow", "color": "#0ea5e9"},
                        {"dataKey": "ai_tech_flow", "name": "Tech / Semi Sector", "color": "#8b5cf6"},
                    ],
                    "items": [
                        {"period": "2026-W40", "total_flow": 18200000, "ai_tech_flow": 11400000},
                        {"period": "2026-W41", "total_flow": 22400000, "ai_tech_flow": 14800000},
                        {"period": "2026-W42", "total_flow": 19500000, "ai_tech_flow": 12900000},
                        {"period": "2026-W43", "total_flow": 31000000, "ai_tech_flow": 21500000},
                        {"period": "2026-W44", "total_flow": 27800000, "ai_tech_flow": 18200000},
                        {"period": "2026-W45", "total_flow": 36400000, "ai_tech_flow": 24900000},
                        {"period": "2026-W46", "total_flow": 32100000, "ai_tech_flow": 22100000},
                    ],
                },
            },
            {
                "id": "chart-sector-donut",
                "widget_type": "pie_chart",
                "title": "Asset & Sector Distribution",
                "description": "Portfolio allocation of congressional transactions",
                "span": 2,
                "data": {
                    "nameKey": "sector",
                    "valueKey": "value",
                    "items": [
                        {"sector": "Information Technology", "value": 168000000, "color": "#10b981"},
                        {"sector": "Health Care & Biotech", "value": 94000000, "color": "#0ea5e9"},
                        {"sector": "Defense & Aerospace", "value": 72000000, "color": "#8b5cf6"},
                        {"sector": "Financial Services", "value": 58000000, "color": "#f59e0b"},
                        {"sector": "Energy & Materials", "value": 46000000, "color": "#ec4899"},
                        {"sector": "Index / ETFs / Funds", "value": 39700000, "color": "#64748b"},
                    ],
                },
            },
            {
                "id": "table-top-assets",
                "widget_type": "data_table",
                "title": "Top Traded Assets Leaderboard",
                "description": "Highest congressional capital allocation targets",
                "span": 2,
                "data": {
                    "columns": [
                        {"key": "ticker", "header": "Ticker", "monospace": True, "width": "w-20"},
                        {"key": "asset_name", "header": "Asset Name"},
                        {"key": "purchases_val", "header": "Total Bought", "align": "right", "monospace": True},
                        {"key": "sales_val", "header": "Total Sold", "align": "right", "monospace": True},
                        {"key": "trades_count", "header": "Trades", "align": "center", "monospace": True},
                        {"key": "sentiment", "header": "Sentiment", "align": "center", "badge": True},
                    ],
                    "rows": [
                        {"ticker": "NVDA", "asset_name": "NVIDIA Corporation", "purchases_val": "$64.2M", "sales_val": "$12.8M", "trades_count": 48, "sentiment": "Purchase"},
                        {"ticker": "MSFT", "asset_name": "Microsoft Corporation", "purchases_val": "$42.5M", "sales_val": "$18.1M", "trades_count": 36, "sentiment": "Purchase"},
                        {"ticker": "AAPL", "asset_name": "Apple Inc.", "purchases_val": "$28.4M", "sales_val": "$34.2M", "trades_count": 29, "sentiment": "Sale"},
                        {"ticker": "AMZN", "asset_name": "Amazon.com, Inc.", "purchases_val": "$31.0M", "sales_val": "$14.5M", "trades_count": 25, "sentiment": "Purchase"},
                        {"ticker": "LMT", "asset_name": "Lockheed Martin Corp.", "purchases_val": "$22.1M", "sales_val": "$5.4M", "trades_count": 18, "sentiment": "Purchase"},
                    ],
                },
            },
        ],
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
