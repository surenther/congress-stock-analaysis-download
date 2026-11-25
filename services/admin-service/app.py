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

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
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

# Base URLs of the services the admin command center orchestrates. Overridable
# via environment for non-Compose deployments.
SERVICE_URLS: Dict[str, str] = {
    "downloader": os.getenv("DOWNLOADER_SERVICE_URL", "http://congress-service:8511"),
    "parser": os.getenv("PARSER_SERVICE_URL", "http://parser-service:8513"),
    "vectorizer": os.getenv("VECTORIZER_SERVICE_URL", "http://vectorizer-service:8514"),
    "auth": os.getenv("AUTH_SERVICE_URL", "http://auth-service:8512"),
    "admin": os.getenv("ADMIN_SERVICE_URL", "http://admin-service:8515"),
    "rag": os.getenv("RAG_SERVICE_URL", "http://rag-service:8516"),
    "litellm": os.getenv("LITELLM_PROXY_URL", "http://litellm-proxy:4000"),
}

# Trigger endpoint per pipeline service.
TRIGGER_PATHS: Dict[str, str] = {
    "downloader": "/api/v1/download/trigger",
    "parser": "/api/v1/parse/trigger",
    "vectorizer": "/api/v1/vectorize/trigger-bulk",
}

# Health probe path per service (LiteLLM uses a different path).
HEALTH_PATHS: Dict[str, str] = {
    "litellm": "/health/liveliness",
}


async def _trigger_service(
    service: str,
    token: Optional[str],
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Proxy a trigger request to a pipeline service using the caller's token."""
    url = SERVICE_URLS.get(service)
    path = TRIGGER_PATHS.get(service)
    if not url or not path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown pipeline service '{service}'.",
        )
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{url.rstrip('/')}{path}", headers=headers, json=body or {}
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Upstream {service} returned {resp.status_code}: {resp.text[:500]}",
        )
    return resp.json()


async def _scheduler_loop() -> None:
    """Periodically trigger due pipeline schedules (checked once per minute)."""
    while True:
        try:
            await asyncio.sleep(60)
            async with pool.acquire() as conn:
                due = await conn.fetch(
                    "SELECT id, service, chamber, interval_minutes "
                    "FROM pipeline_schedules "
                    "WHERE enabled = TRUE "
                    "AND (next_run_at IS NULL OR next_run_at <= NOW())"
                )
            for row in due:
                body = {"chamber": row["chamber"]} if row["chamber"] else {}
                try:
                    await _trigger_service(row["service"], None, body)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning(
                        "Scheduled trigger failed for %s: %s", row["service"], exc
                    )
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE pipeline_schedules SET last_run_at = NOW(), "
                        "next_run_at = NOW() + ($1 || ' minutes')::interval "
                        "WHERE id = $2",
                        str(row["interval_minutes"]),
                        row["id"],
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Scheduler loop error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the shared connection pool and start the scheduler."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    set_pool(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pipeline_schedules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                service VARCHAR(32) NOT NULL,
                chamber VARCHAR(16),
                interval_minutes INTEGER NOT NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                last_run_at TIMESTAMPTZ,
                next_run_at TIMESTAMPTZ,
                created_by VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    scheduler_task = asyncio.create_task(_scheduler_loop())
    yield
    scheduler_task.cancel()
    await pool.close()


app = FastAPI(
    title="Congressional Disclosure Admin / Observability Microservice",
    description=(
        "Read-only aggregation API over the downloader, parser, and vectorizer "
        "job tables. All endpoints require the ``admin`` role.\n\n"
        "The three domain services share one PostgreSQL database, so this "
        "service queries their job tables directly and normalizes the results "
        "into a single consistent shape for dashboards and operators.\n\n"
        "### Endpoints\n"
        "* `GET /api/v1/jobs` — unified, paginated list of jobs across all "
        "services (filter by `service` and `status`).\n"
        "* `GET /api/v1/jobs/summary` — counts grouped by service and status.\n"
        "* `GET /api/v1/jobs/{service}/{job_id}` — one job's normalized detail.\n"
        "* `GET /api/v1/jobs/{service}/{job_id}/items` — paginated per-document "
        "outcomes for one job.\n\n"
        "`service` is one of `downloader`, `parser`, or `vectorizer`.\n\n"
        "### Authorization\n"
        "Every `/api/v1/jobs/*` route requires a Bearer JWT carrying the "
        "`admin` role; unauthenticated requests return `401` and authenticated "
        "requests lacking the role return `403`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "General", "description": "Health and readiness probes."},
        {
            "name": "Jobs",
            "description": (
                "Read-only cross-service job aggregation. All routes require "
                "the `admin` role."
            ),
        },
    ],
)


# ==============================================================================
# RESPONSE MODELS
# ==============================================================================

class JobSummaryItem(BaseModel):
    """A single normalized job row."""

    service: str = Field(..., description="downloader, parser, or vectorizer.")
    job_id: str = Field(..., description="UUID of the job.")
    status: str = Field(
        ...,
        description="PENDING, IN_PROGRESS, COMPLETED, FAILED, or CANCELLED.",
    )
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


def _parse_iso_timestamp(value: Optional[str], field: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp query param, or raise HTTP 422 if invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid '{field}' timestamp; expected ISO 8601.",
        )


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


# ==============================================================================
# PIPELINE ORCHESTRATION
# ==============================================================================

class PipelineTriggerRequest(BaseModel):
    """Body for a manual pipeline trigger."""

    chamber: Optional[str] = Field(default=None, description="house, senate, or all.")
    doc_ids: Optional[List[str]] = Field(default=None, description="Optional doc ids.")
    force: bool = Field(default=False, description="Reprocess already-done docs.")
    limit: Optional[int] = Field(
        default=None,
        ge=0,
        description="Max new documents to queue (0 = all). Forwarded to the service.",
    )


class ScheduleCreate(BaseModel):
    """Body for creating a recurring pipeline schedule."""

    service: str = Field(..., description="downloader, parser, or vectorizer.")
    chamber: Optional[str] = None
    interval_minutes: int = Field(..., ge=1, le=10080)


def _bearer(request: Request) -> Optional[str]:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header.split(" ", 1)[1].strip()
    return None


@app.post(
    "/api/v1/admin/pipeline/{service}/trigger",
    tags=["Pipeline"],
    dependencies=[Depends(require_role(["admin"]))],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
        404: {"description": "Unknown pipeline service."},
    },
)
async def trigger_pipeline(
    service: str,
    body: PipelineTriggerRequest,
    request: Request,
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Manually trigger a pipeline service (downloader, parser, vectorizer)."""
    svc = service.lower().strip()
    if svc not in TRIGGER_PATHS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown pipeline service '{service}'.",
        )
    trigger_body: Dict[str, Any] = {}
    if body.chamber:
        trigger_body["chamber"] = body.chamber
    if body.doc_ids:
        trigger_body["doc_ids"] = body.doc_ids
    if body.force:
        trigger_body["force"] = True
    if body.limit is not None:
        trigger_body["limit"] = body.limit
    result = await _trigger_service(svc, _bearer(request), trigger_body)
    logger.info("Pipeline trigger service=%s by=%s", svc, payload.get("sub"))
    return {"service": svc, "result": result}


@app.post(
    "/api/v1/admin/pipeline/jobs/{service}/{job_id}/retry",
    tags=["Pipeline"],
    dependencies=[Depends(require_role(["admin"]))],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
        404: {"description": "Unknown service or job not found."},
    },
)
async def retry_job(
    service: str,
    job_id: str,
    request: Request,
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Re-trigger the failed documents of a pipeline job (single-click retry)."""
    svc = _validate_service(service)
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    items_table = SERVICE_TABLES[svc]["items"]
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT doc_id FROM {items_table} "
            f"WHERE job_id = $1 AND status = 'FAILED'",
            job_uuid,
        )
    doc_ids = [row["doc_id"] for row in rows if row["doc_id"]]
    if not doc_ids:
        return {"service": svc, "retried": 0, "message": "No failed items to retry."}
    result = await _trigger_service(
        svc, _bearer(request), {"doc_ids": doc_ids, "force": True}
    )
    logger.info(
        "Retry service=%s job=%s failed_items=%d by=%s",
        svc, job_id, len(doc_ids), payload.get("sub"),
    )
    return {
        "service": svc,
        "retried": len(doc_ids),
        "doc_ids": doc_ids,
        "result": result,
    }


@app.post(
    "/api/v1/admin/pipeline/jobs/{service}/{job_id}/cancel",
    tags=["Pipeline"],
    dependencies=[Depends(require_role(["admin"]))],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
        404: {"description": "Unknown service or job not found."},
    },
)
async def cancel_job(
    service: str,
    job_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Request cooperative cancellation of a running pipeline job.

    Sets the job's ``cancel_requested`` flag; the owning service stops at the
    next document/file boundary and marks the job ``CANCELLED``. Jobs that are
    already in a terminal state are reported as-is (nothing to cancel).
    """
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
            f"SELECT status FROM {table} WHERE job_id = $1", job_uuid
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            )
        current_status = row["status"]
        if current_status not in ("PENDING", "IN_PROGRESS"):
            return {
                "service": svc,
                "job_id": str(job_uuid),
                "status": current_status,
                "cancel_requested": False,
                "message": f"Job is already {current_status}; nothing to cancel.",
            }
        await conn.execute(
            f"UPDATE {table} SET cancel_requested = TRUE, updated_at = NOW() "
            f"WHERE job_id = $1",
            job_uuid,
        )

    logger.info(
        "Cancel requested service=%s job=%s by=%s", svc, job_id, payload.get("sub")
    )
    return {
        "service": svc,
        "job_id": str(job_uuid),
        "status": current_status,
        "cancel_requested": True,
        "message": (
            "Cancellation requested; the job will stop at the next boundary."
        ),
    }


# ==============================================================================
# CLUSTER HEALTH
# ==============================================================================

@app.get(
    "/api/v1/admin/health/cluster",
    tags=["Health"],
    dependencies=[Depends(require_role(["admin"]))],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
    },
)
async def cluster_health():
    """Probe every microservice's health endpoint and report latency."""
    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in SERVICE_URLS.items():
            path = HEALTH_PATHS.get(name, "/health")
            start = time.perf_counter()
            try:
                resp = await client.get(f"{url.rstrip('/')}{path}")
                latency = (time.perf_counter() - start) * 1000
                results.append(
                    {
                        "service": name,
                        "url": url,
                        "status": "healthy" if resp.status_code < 400 else "unhealthy",
                        "http_status": resp.status_code,
                        "latency_ms": round(latency, 1),
                    }
                )
            except Exception as exc:  # pragma: no cover - network dependent
                latency = (time.perf_counter() - start) * 1000
                results.append(
                    {
                        "service": name,
                        "url": url,
                        "status": "unreachable",
                        "http_status": None,
                        "latency_ms": round(latency, 1),
                        "error": str(exc)[:200],
                    }
                )
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": results,
    }


# ==============================================================================
# AUDIT LOG
# ==============================================================================

@app.get(
    "/api/v1/admin/audit-log",
    tags=["Audit"],
    dependencies=[Depends(require_role(["admin"]))],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the admin role."},
    },
)
async def audit_log(
    action: Optional[str] = Query(default=None, description="Filter by action."),
    actor: Optional[str] = Query(
        default=None, description="Filter by actor username (exact match)."
    ),
    target_type: Optional[str] = Query(
        default=None, description="Filter by target type (e.g. 'user')."
    ),
    target_id: Optional[str] = Query(
        default=None, description="Filter by target id (exact match)."
    ),
    since: Optional[str] = Query(
        default=None, description="ISO 8601 lower bound on created_at (inclusive)."
    ),
    until: Optional[str] = Query(
        default=None, description="ISO 8601 upper bound on created_at (inclusive)."
    ),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return recent audit-log entries (admin only).

    Supports optional filters by ``action``, ``actor``, ``target_type``,
    ``target_id`` and a ``since``/``until`` created-at window. All filters are
    combined with AND and applied via parameterized SQL.
    """
    since_dt = _parse_iso_timestamp(since, "since")
    until_dt = _parse_iso_timestamp(until, "until")
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT to_regclass('public.audit_log') IS NOT NULL"
        )
        if not exists:
            return {"total": 0, "limit": limit, "offset": offset, "entries": []}
        params: List[Any] = []
        clauses: List[str] = []
        if action:
            params.append(action)
            clauses.append(f"action = ${len(params)}")
        if actor:
            params.append(actor)
            clauses.append(f"actor_username = ${len(params)}")
        if target_type:
            params.append(target_type)
            clauses.append(f"target_type = ${len(params)}")
        if target_id:
            params.append(target_id)
            clauses.append(f"target_id = ${len(params)}")
        if since_dt is not None:
            params.append(since_dt)
            clauses.append(f"created_at >= ${len(params)}")
        if until_dt is not None:
            params.append(until_dt)
            clauses.append(f"created_at <= ${len(params)}")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM audit_log {where}", *params
        )
        params.append(limit)
        limit_idx = len(params)
        params.append(offset)
        offset_idx = len(params)
        rows = await conn.fetch(
            f"SELECT id, actor_username, action, target_type, target_id, "
            f"metadata, ip, created_at FROM audit_log {where} "
            f"ORDER BY created_at DESC LIMIT ${limit_idx} OFFSET ${offset_idx}",
            *params,
        )
    return {
        "total": total or 0,
        "limit": limit,
        "offset": offset,
        "entries": [
            {
                "id": row["id"],
                "actor_username": row["actor_username"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "metadata": row["metadata"],
                "ip": row["ip"],
                "created_at": _iso(row["created_at"]),
            }
            for row in rows
        ],
    }


# ==============================================================================
# SCHEDULES
# ==============================================================================

@app.get(
    "/api/v1/admin/pipeline/schedule",
    tags=["Pipeline"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def list_schedules():
    """List recurring pipeline schedules (admin only)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, service, chamber, interval_minutes, enabled, "
            "last_run_at, next_run_at, created_by, created_at "
            "FROM pipeline_schedules ORDER BY created_at DESC"
        )
    return {
        "schedules": [
            {
                "id": str(row["id"]),
                "service": row["service"],
                "chamber": row["chamber"],
                "interval_minutes": row["interval_minutes"],
                "enabled": row["enabled"],
                "last_run_at": _iso(row["last_run_at"]),
                "next_run_at": _iso(row["next_run_at"]),
                "created_by": row["created_by"],
                "created_at": _iso(row["created_at"]),
            }
            for row in rows
        ]
    }


@app.post(
    "/api/v1/admin/pipeline/schedule",
    status_code=status.HTTP_201_CREATED,
    tags=["Pipeline"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def create_schedule(
    body: ScheduleCreate,
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Create a recurring pipeline schedule (admin only)."""
    svc = body.service.lower().strip()
    if svc not in TRIGGER_PATHS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown pipeline service '{body.service}'.",
        )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO pipeline_schedules "
            "(service, chamber, interval_minutes, next_run_at, created_by) "
            "VALUES ($1, $2, $3, NOW() + ($3 || ' minutes')::interval, $4) "
            "RETURNING id, service, chamber, interval_minutes, enabled, next_run_at",
            svc,
            body.chamber,
            body.interval_minutes,
            payload.get("sub"),
        )
    return {
        "id": str(row["id"]),
        "service": row["service"],
        "chamber": row["chamber"],
        "interval_minutes": row["interval_minutes"],
        "enabled": row["enabled"],
        "next_run_at": _iso(row["next_run_at"]),
    }


@app.delete(
    "/api/v1/admin/pipeline/schedule/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Pipeline"],
    dependencies=[Depends(require_role(["admin"]))],
)
async def delete_schedule(schedule_id: str):
    """Delete a recurring pipeline schedule (admin only)."""
    try:
        schedule_uuid = uuid.UUID(schedule_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found"
        )
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM pipeline_schedules WHERE id = $1", schedule_uuid
        )
    if result.endswith("0"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found"
        )
    return None
