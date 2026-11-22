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

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import Depends, FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
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
    filer_name: Optional[str] = None
    chamber: Optional[str] = None
    ticker: Optional[str] = None
    similarity_score: Optional[float] = None


class RagQueryResponse(BaseModel):
    query: str
    answer: str
    user_chamber_access: List[str]
    sources: List[SourceCitation]


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

    sources = await retriever.hybrid_search(
        pool=pool,
        query=body.prompt,
        allowed_chambers=allowed_chambers,
        top_k=body.top_k,
        ticker=filters.ticker,
        is_market_trade=filters.is_market_trade,
        start_date=filters.start_date,
        end_date=filters.end_date,
    )

    synthesis = rag_engine.synthesize(
        query=body.prompt,
        sources=sources,
        allowed_chambers=allowed_chambers,
        user_id=payload.get("sub"),
        model=body.model,
    )

    logger.info(
        "RAG query user=%s chambers=%s sources=%d cost=$%.6f",
        payload.get("sub"),
        allowed_chambers,
        len(sources),
        synthesis.get("cost", 0.0),
    )

    return {
        "query": body.prompt,
        "answer": synthesis["answer"],
        "user_chamber_access": allowed_chambers,
        "sources": synthesis["sources"],
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
