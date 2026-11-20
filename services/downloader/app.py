#!/usr/bin/env python3
"""
Congressional Financial Disclosures Microservice API

FastAPI-based microservice to trigger and monitor asynchronous download jobs
for U.S. House of Representatives and U.S. Senate financial disclosure filings.
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import asyncpg
from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

import download_filings
from auth_utils import require_role, set_pool

# ==============================================================================
# LOGGING
# ==============================================================================
# A dedicated "downloader" logger with its own handler so our INFO/DEBUG lines
# always appear in `docker logs` regardless of uvicorn's logging configuration.
# Set LOG_LEVEL=DEBUG for verbose detail.
logger = logging.getLogger("downloader")
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and initialize the jobs table on startup."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    # Enable DB-backed authorization checks for downstream RBAC dependencies.
    set_pool(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id UUID PRIMARY KEY,
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                error_message TEXT
            );
            """
        )
    yield
    await pool.close()


app = FastAPI(
    title="Congressional Financial Disclosures Microservice",
    description=(
        "Microservice to download and store U.S. House of Representatives and "
        "U.S. Senate financial disclosure filings (STOCK Act Periodic Transaction Reports & Annual Reports) "
        "directly into an external mounted volume.\n\n"
        "### Trigger semantics\n"
        "`POST /api/v1/download/trigger` scans candidate filings, skips any whose "
        "PDF/HTML already exists on the `/data` volume, and queues the first "
        "`limit` **new** filings. `limit: 0` processes all unprocessed filings; "
        "`force: true` bypasses deduplication and re-downloads up to `limit` "
        "filings. The response reports `total_candidates_scanned`, "
        "`skipped_already_downloaded`, and `queued_for_download` immediately.\n\n"
        "### Authorization\n"
        "All `/api/v1/download/*` routes require a Bearer JWT. Triggering requires "
        "the `admin` role; status retrieval allows `admin` or `user`."
    ),
    version="3.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "General", "description": "Health and readiness probes."},
        {
            "name": "Async Download",
            "description": (
                "Asynchronous download jobs. Triggering requires the `admin` "
                "role; status retrieval allows `admin` or `user`."
            ),
        },
    ],
)


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
    # A strict CSP is applied to API responses; the interactive docs (/docs,
    # /redoc) are exempt because they load CDN assets.
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
    return response


class AsyncDownloadRequest(BaseModel):
    chamber: str = Field(..., description="Chamber to download: 'house', 'senate', or 'all'")
    year: Optional[str] = Field(default=None, description="Reporting year (e.g. '2026')")
    limit: Optional[int] = Field(
        default=0,
        description=(
            "Maximum number of NEW/unprocessed filings to download. Already-present "
            "files are skipped and do not count toward the limit. 0 = process all "
            "unprocessed filings."
        ),
    )
    max_downloads: Optional[int] = Field(
        default=0,
        description="Deprecated alias for 'limit' (kept for backward compatibility).",
    )
    force: Optional[bool] = Field(
        default=False,
        description="Bypass deduplication and re-download up to 'limit' filings.",
    )
    force_download: Optional[bool] = Field(
        default=False,
        description="Deprecated alias for 'force' (kept for backward compatibility).",
    )


class AsyncDownloadTriggerResponse(BaseModel):
    """Response returned by ``POST /api/v1/download/trigger`` (202 Accepted)."""

    job_id: str = Field(..., description="UUID of the enqueued download job.")
    total_candidates_scanned: int = Field(
        ..., description="Candidate filings inspected during queue selection."
    )
    skipped_already_downloaded: int = Field(
        ..., description="Candidates skipped because the file already exists."
    )
    queued_for_download: int = Field(
        ..., description="New filings queued for download."
    )
    status: str = Field(..., description="Initial job status (IN_PROGRESS).")


async def _update_job_status(
    job_id: uuid.UUID, status: str, error_message: Optional[str] = None
):
    """Update the status of a job in PostgreSQL."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status = $1, updated_at = NOW(), error_message = $2 WHERE job_id = $3",
            status,
            error_message,
            job_id,
        )


async def _execute_async_download(job_id: uuid.UUID, plans: list):
    """Background worker that downloads the pre-built queue for each chamber."""
    logger.info(
        "Job %s [download] started: %d chamber plan(s)", job_id, len(plans)
    )
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        for plan in plans:
            queue = plan["queue"]
            if not queue:
                logger.info(
                    "Job %s [download] %s: nothing queued (scanned=%d skipped=%d)",
                    job_id, plan["cfg"]["CHAMBER"],
                    plan["total_candidates_scanned"],
                    plan["skipped_already_downloaded"],
                )
                continue
            logger.info(
                "Job %s [download] %s: processing %d queued filing(s)",
                job_id, plan["cfg"]["CHAMBER"], len(queue),
            )
            await asyncio.to_thread(
                download_filings.process_download_queue,
                queue,
                plan["base_output_dir"],
                plan["cfg"]["YEAR"],
                plan["cfg"],
            )
            logger.info(
                "Job %s [download] %s pipeline finished",
                job_id, plan["cfg"]["CHAMBER"],
            )
        await _update_job_status(job_id, "COMPLETED")
        logger.info("Job %s [download] completed", job_id)
    except Exception as e:
        await _update_job_status(job_id, "FAILED", str(e))
        logger.error("Job %s [download] failed: %s", job_id, e)


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get(
    "/health",
    summary="Health check",
    response_description="Minimal service health status.",
    tags=["General"],
)
def health():
    """Health check endpoint for Docker container probes.

    Returns only a minimal status so no internal paths or configuration are
    disclosed to unauthenticated callers.
    """
    return {"status": "healthy"}


# ==============================================================================
# ASYNC JOB ENDPOINTS (PostgreSQL-backed)
# ==============================================================================

@app.post(
    "/api/v1/download/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AsyncDownloadTriggerResponse,
    summary="Trigger an asynchronous download job",
    response_description=(
        "The job was accepted; the response reports how many candidates were "
        "scanned, skipped, and queued."
    ),
    tags=["Async Download"],
    responses={
        400: {"description": "Invalid chamber value."},
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' role."},
        502: {"description": "Failed to build the download queue."},
    },
)
async def trigger_download(
    background_tasks: BackgroundTasks,
    request: AsyncDownloadRequest = Body(
        ...,
        openapi_examples={
            "house_all_new": {
                "summary": "House — download all new filings",
                "value": {"chamber": "house", "year": "2026", "limit": 0},
            },
            "senate_limited": {
                "summary": "Senate — download at most 10 new filings",
                "value": {"chamber": "senate", "year": "2026", "limit": 10},
            },
            "all_force": {
                "summary": "All chambers — force re-download up to 5 filings",
                "value": {"chamber": "all", "limit": 5, "force": True},
            },
        },
    ),
    payload: dict = Depends(require_role(["admin"])),
):
    """Trigger a download job asynchronously and return a job ID immediately.

    Requires the ``admin`` role.

    The candidate scan and deduplication check run synchronously so the response
    can report how many candidates were inspected, how many were already present,
    and how many were queued. ``limit`` caps the number of **new** downloads; ``0``
    means "process all unprocessed candidates".
    """
    if request.chamber not in ("house", "senate", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: house, senate, all",
        )

    # ``limit`` is the canonical field; ``max_downloads`` is a backward-compatible
    # alias. ``force`` is canonical; ``force_download`` is the alias.
    limit = request.limit if request.limit is not None else request.max_downloads
    limit = limit or 0
    force = bool(request.force or request.force_download)

    job_id = uuid.uuid4()
    logger.info(
        "Received download trigger: job=%s chamber=%s year=%s limit=%s "
        "force=%s requested_by=%s",
        job_id, request.chamber, request.year, limit,
        force, payload.get("sub"),
    )

    # Build the queue(s) synchronously so the response can report scan counters.
    chambers = ["house", "senate"] if request.chamber == "all" else [request.chamber]
    plans = []
    total_candidates_scanned = 0
    skipped_already_downloaded = 0
    queued_for_download = 0
    remaining = limit
    try:
        for ch in chambers:
            env_file = ".env.house" if ch == "house" else ".env.senate"
            plan = await asyncio.to_thread(
                download_filings.build_download_queue,
                chamber=ch,
                env_file_path=env_file,
                year=request.year,
                max_downloads=remaining,
                force_download=force,
            )
            plans.append(plan)
            total_candidates_scanned += plan["total_candidates_scanned"]
            skipped_already_downloaded += plan["skipped_already_downloaded"]
            queued_for_download += plan["queued_for_download"]
            if remaining > 0:
                remaining = max(0, remaining - plan["queued_for_download"])
                if remaining == 0:
                    break
    except Exception as exc:
        logger.error("Job %s [download] queue build failed: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to build download queue: {exc}",
        )

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO jobs (job_id, status) VALUES ($1, $2)",
            job_id,
            "IN_PROGRESS",
        )

    background_tasks.add_task(_execute_async_download, job_id, plans)

    return {
        "job_id": str(job_id),
        "total_candidates_scanned": total_candidates_scanned,
        "skipped_already_downloaded": skipped_already_downloaded,
        "queued_for_download": queued_for_download,
        "status": "IN_PROGRESS",
    }


@app.get(
    "/api/v1/download/status/{job_id}",
    summary="Get the status of a download job",
    response_description="The current state of the job.",
    tags=["Async Download"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Job not found."},
    },
)
async def get_download_status(
    job_id: str,
    payload: dict = Depends(require_role(["admin", "user"])),
):
    """Return the current status of an asynchronous download job.

    Allowed for the ``admin`` and ``user`` roles.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    async with pool.acquire() as conn:
        job = await conn.fetchrow(
            "SELECT job_id, status, created_at, updated_at, error_message "
            "FROM jobs WHERE job_id = $1",
            job_uuid,
        )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return {
        "job_id": str(job["job_id"]),
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "error_message": job["error_message"],
    }
