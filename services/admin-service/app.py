#!/usr/bin/env python3
"""
Admin / Observability Microservice API

Read-only FastAPI service that aggregates job state across the downloader,
parser, and vectorizer services. All three services share the same PostgreSQL
database, so this service queries their job tables directly and normalizes the
results into a single consistent shape.

All endpoints require the ``admin`` role.

Endpoints
---------
* ``GET /health`` — liveness probe.
* ``GET /api/v1/jobs`` — unified paginated list across all services.
* ``GET /api/v1/jobs/summary`` — counts grouped by service and status.
* ``GET /api/v1/jobs/{service}/{job_id}`` — single job detail.
* ``GET /api/v1/jobs/{service}/{job_id}/items`` — per-document outcomes.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from auth_utils import require_role, set_pool

logger = logging.getLogger("admin-service")
if not logger.handlers:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL must be set (postgresql://user:password@host:port/db)."
    )

pool: Optional[asyncpg.Pool] = None

# Mapping of service name -> (jobs table, items table, has_cost_column).
# The downloader's items table has no cost column, so cost is projected as 0.
SERVICE_TABLES: Dict[str, Dict[str, Any]] = {
    "downloader": {
        "jobs": "jobs",
        "items": "download_job_items",
        "has_cost": False,
    },
    "parser": {
        "jobs": "parse_jobs",
        "items": "parse_job_items",
        "has_cost": True,
    },
    "vectorizer": {
        "jobs": "vectorizer_jobs",
        "items": "vectorizer_job_items",
        "has_cost": True,
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the shared connection pool on startup."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    set_pool(pool)
    yield
    await pool.close()


app = FastAPI(
    title="Congressional Disclosure Admin / Observability Microservice",
    description=(
        "Read-only aggregation API over the downloader, parser, and vectorizer "
        "job tables. All endpoints require the ``admin`` role.\n\n"
        "The three domain services share one PostgreSQL database, so this "
        "service queries their job tables directly and normalizes the results "
        "into a single consistent shape for dashboards and operators."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ==============================================================================
# RESPONSE MODELS
# ==============================================================================

class JobSummaryItem(BaseModel):
    """A single normalized job row."""

    service: str = Field(..., description="downloader, parser, or vectorizer.")
    job_id: str = Field(..., description="UUID of the job.")
    status: str = Field(..., description="PENDING, IN_PROGRESS, COMPLETED, or FAILED.")
    chamber: Optional[str] = Field(default=None, description="Chamber or 'all'.")
    requested_by: Optional[str] = Field(default=None, description="Triggering user.")
    mode: Optional[str] = Field(default=None, description="'single' or 'bulk'.")
    total_documents: Optional[int] = Field(default=None, description="Total documents.")
    processed_documents: Optional[int] = Field(
        default=None, description="Documents processed so far."
    )
    total_cost: Optional[float] = Field(default=None, description="Total LLM cost (USD).")
    created_at: Optional[str] = Field(default=None, description="Creation timestamp.")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp.")
    error_message: Optional[str] = Field(default=None, description="Error detail.")


class JobListResponse(BaseModel):
    """Paginated unified job list."""

    total: int = Field(..., description="Total jobs matching the filter.")
    limit: int = Field(..., description="Page size.")
    offset: int = Field(..., description="Page offset.")
    jobs: List[JobSummaryItem] = Field(..., description="Page of jobs.")


class ServiceStatusCount(BaseModel):
    """Count of jobs for one service/status pair."""

    service: str = Field(..., description="Service name.")
    status: str = Field(..., description="Job status.")
    count: int = Field(..., description="Number of jobs.")


class JobSummaryResponse(BaseModel):
    """Counts grouped by service and status."""

    total: int = Field(..., description="Total jobs across all services.")
    by_service: Dict[str, int] = Field(..., description="Counts keyed by service.")
    by_status: Dict[str, int] = Field(..., description="Counts keyed by status.")
    breakdown: List[ServiceStatusCount] = Field(
        ..., description="Counts for each service/status pair."
    )


class JobItem(BaseModel):
    """A single per-document outcome."""

    doc_id: Optional[str] = Field(default=None, description="Document ID.")
    file_path: Optional[str] = Field(default=None, description="Relative file path.")
    status: str = Field(..., description="SUCCESS, SKIPPED, or FAILED.")
    detail: Optional[str] = Field(default=None, description="Error detail or skip reason.")
    cost: Optional[float] = Field(default=None, description="LLM cost (USD).")
    created_at: Optional[str] = Field(default=None, description="Recorded timestamp.")


class JobItemsResponse(BaseModel):
    """Paginated per-document outcomes."""

    service: str = Field(..., description="Service name.")
    job_id: str = Field(..., description="UUID of the job.")
    total: int = Field(..., description="Items matching the filter.")
    limit: int = Field(..., description="Page size.")
    offset: int = Field(..., description="Page offset.")
    items: List[JobItem] = Field(..., description="Page of items.")


# ==============================================================================
# HELPERS
# ==============================================================================

def _validate_service(service: str) -> str:
    """Normalize and validate a service name."""
    key = service.lower().strip()
    if key not in SERVICE_TABLES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown service '{service}'. "
                f"Expected one of: {', '.join(sorted(SERVICE_TABLES))}."
            ),
        )
    return key


def _iso(value: Any) -> Optional[str]:
    """Convert a datetime to ISO 8601, or return None."""
    return value.isoformat() if value else None


def _normalize_job(service: str, row: asyncpg.Record) -> Dict[str, Any]:
    """Normalize a service-specific job row into the common shape."""
    return {
        "service": service,
        "job_id": str(row["job_id"]),
        "status": row["status"],
        "chamber": row.get("chamber"),
        "requested_by": row.get("requested_by"),
        "mode": row.get("mode"),
        "total_documents": row.get("total_documents"),
        "processed_documents": row.get("processed_documents"),
        "total_cost": row.get("total_cost"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "error_message": row.get("error_message"),
    }


def _union_jobs_query(
    service: Optional[str], status_filter: Optional[str]
) -> tuple[str, List[Any]]:
    """Build a UNION ALL query across the selected service job tables.

    Each service's table is projected into the common column set. The
    downloader's ``jobs`` table lacks mode/total_documents/processed_documents/
    total_cost, so those are projected as NULL.
    """
    services = [service] if service else list(SERVICE_TABLES.keys())
    selects: List[str] = []
    params: List[Any] = []

    for svc in services:
        table = SERVICE_TABLES[svc]["jobs"]
        if svc == "downloader":
            selects.append(
                f"SELECT '{svc}' AS service, job_id, status, chamber, requested_by, "
                f"NULL::varchar AS mode, NULL::integer AS total_documents, "
                f"NULL::integer AS processed_documents, NULL::double precision AS total_cost, "
                f"created_at, updated_at, error_message FROM {table}"
            )
        else:
            selects.append(
                f"SELECT '{svc}' AS service, job_id, status, chamber, requested_by, "
                f"mode, total_documents, processed_documents, total_cost, "
                f"created_at, updated_at, error_message FROM {table}"
            )

    union = " UNION ALL ".join(selects)
    where_clauses: List[str] = []
    if status_filter:
        params.append(status_filter.upper())
        where_clauses.append(f"status = ${len(params)}")

    query = f"SELECT * FROM ({union}) AS all_jobs"
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    return query, params


# ==============================================================================
# ENDPOINTS
# ==============================================================================

@app.get(
    "/health",
    summary="Health check",
    response_description="Minimal service health status.",
    tags=["General"],
)
def health():
    """Liveness probe for Docker/container orchestration."""
    return {"status": "healthy"}


@app.get(
    "/api/v1/jobs",
    response_model=JobListResponse,
    summary="List jobs across all services",
    response_description="Paginated, normalized job list.",
    tags=["Jobs"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
    },
)
async def list_jobs(
    service: Optional[str] = Query(
        default=None,
        description="Filter by service: downloader, parser, or vectorizer.",
    ),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by job status (PENDING, IN_PROGRESS, COMPLETED, FAILED).",
    ),
    limit: int = Query(default=50, ge=1, le=500, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Return a unified, paginated list of jobs across all services.

    Admin-only. Results are ordered by ``created_at`` descending (newest first).
    """
    svc = _validate_service(service) if service else None
    query, params = _union_jobs_query(svc, status_filter)

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM ({query}) AS counted", *params
        )
        rows = await conn.fetch(
            f"{query} ORDER BY created_at DESC "
            f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params,
            limit,
            offset,
        )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "jobs": [_normalize_job(row["service"], row) for row in rows],
    }


@app.get(
    "/api/v1/jobs/summary",
    response_model=JobSummaryResponse,
    summary="Summarize job counts by service and status",
    response_description="Counts grouped by service and status.",
    tags=["Jobs"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
    },
)
async def jobs_summary(
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Return job counts grouped by service and status.

    Admin-only. Useful for dashboard tiles and alerting.
    """
    query, params = _union_jobs_query(None, None)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT service, status, COUNT(*) AS count FROM ({query}) AS all_jobs "
            f"GROUP BY service, status ORDER BY service, status",
            *params,
        )

    by_service: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    breakdown: List[Dict[str, Any]] = []
    total = 0
    for row in rows:
        count = int(row["count"])
        total += count
        by_service[row["service"]] = by_service.get(row["service"], 0) + count
        by_status[row["status"]] = by_status.get(row["status"], 0) + count
        breakdown.append(
            {"service": row["service"], "status": row["status"], "count": count}
        )

    return {
        "total": total,
        "by_service": by_service,
        "by_status": by_status,
        "breakdown": breakdown,
    }


@app.get(
    "/api/v1/jobs/{service}/{job_id}",
    response_model=JobSummaryItem,
    summary="Get a single job's detail",
    response_description="Normalized job detail.",
    tags=["Jobs"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
        404: {"description": "Unknown service or job not found."},
    },
)
async def get_job(
    service: str,
    job_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Return a single job's normalized detail. Admin-only."""
    svc = _validate_service(service)
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    table = SERVICE_TABLES[svc]["jobs"]
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT * FROM {table} WHERE job_id = $1", job_uuid
        )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return _normalize_job(svc, row)


@app.get(
    "/api/v1/jobs/{service}/{job_id}/items",
    response_model=JobItemsResponse,
    summary="List per-document outcomes for a job",
    response_description="Paginated per-document results.",
    tags=["Jobs"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
        404: {"description": "Unknown service or job not found."},
    },
)
async def get_job_items(
    service: str,
    job_id: str,
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by item status (SUCCESS, SKIPPED, FAILED).",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Return paginated per-document outcomes for a job. Admin-only."""
    svc = _validate_service(service)
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    jobs_table = SERVICE_TABLES[svc]["jobs"]
    items_table = SERVICE_TABLES[svc]["items"]
    has_cost = SERVICE_TABLES[svc]["has_cost"]

    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            f"SELECT 1 FROM {jobs_table} WHERE job_id = $1", job_uuid
        )
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            )

        params: List[Any] = [job_uuid]
        where = "WHERE job_id = $1"
        if status_filter:
            params.append(status_filter.upper())
            where += f" AND status = ${len(params)}"

        cost_expr = "cost" if has_cost else "0::double precision AS cost"
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM {items_table} {where}", *params
        )
        rows = await conn.fetch(
            f"SELECT doc_id, file_path, status, detail, {cost_expr}, created_at "
            f"FROM {items_table} {where} "
            f"ORDER BY id LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params,
            limit,
            offset,
        )

    return {
        "service": svc,
        "job_id": str(job_uuid),
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "doc_id": row["doc_id"],
                "file_path": row["file_path"],
                "status": row["status"],
                "detail": row["detail"],
                "cost": row["cost"],
                "created_at": _iso(row["created_at"]),
            }
            for row in rows
        ],
    }
