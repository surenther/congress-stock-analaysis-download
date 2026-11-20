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
from typing import List, Optional

import asyncpg
from fastapi import (
    BackgroundTasks,
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    status,
)
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

# Advisory-lock key used to serialize concurrent trigger requests so two callers
# cannot both observe an idle system and start overlapping download runs (which
# would compete for bandwidth and hammer the House/Senate sites).
_TRIGGER_ADVISORY_LOCK = 0x444C4F44  # "DLOD"

# A PENDING/IN_PROGRESS job whose row has not been updated for this many hours is
# considered stale (e.g. the container was killed mid-run) and is reaped so it
# cannot block every future trigger forever. Set to 0 to disable reaping.
STALE_JOB_HOURS = float(os.getenv("DOWNLOADER_STALE_JOB_HOURS", "2"))


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
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS chamber VARCHAR(20);
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS requested_by VARCHAR(255);

            CREATE TABLE IF NOT EXISTS download_job_items (
                id BIGSERIAL PRIMARY KEY,
                job_id UUID NOT NULL,
                doc_id VARCHAR(64),
                file_path TEXT,
                status VARCHAR(20) NOT NULL,
                detail TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_download_job_items_job
                ON download_job_items(job_id, status);
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
        "### Concurrency\n"
        "Only one download job may run at a time. A trigger received while a job "
        "is `PENDING` or `IN_PROGRESS` is rejected with `409 Conflict` (the "
        "response names the running job), so overlapping runs cannot compete for "
        "bandwidth or hammer the House/Senate sites. A job that stalls without "
        "progress is reaped after `DOWNLOADER_STALE_JOB_HOURS` so it cannot block "
        "future triggers forever.\n\n"
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
            "Maximum number of NEW/unprocessed filings to download PER CHAMBER. "
            "Already-present files are skipped and do not count toward the limit. "
            "With chamber='all', the limit applies independently to House and "
            "Senate (e.g. limit=5 queues up to 5 House AND up to 5 Senate filings). "
            "0 = process all unprocessed filings."
        ),
    )
    max_downloads: Optional[int] = Field(
        default=0,
        description=(
            "Deprecated alias for 'limit' (kept for backward compatibility). "
            "Also applied per chamber."
        ),
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


class DownloadJobItem(BaseModel):
    """A single per-file outcome within a download job."""

    doc_id: Optional[str] = Field(default=None, description="Document ID.")
    file_path: Optional[str] = Field(
        default=None, description="Relative path on the /data volume."
    )
    status: str = Field(..., description="SUCCESS, SKIPPED, or FAILED.")
    detail: Optional[str] = Field(
        default=None, description="Error detail or skip reason."
    )
    created_at: Optional[str] = Field(
        default=None, description="When the item was recorded (ISO 8601)."
    )


class DownloadJobItemsResponse(BaseModel):
    """Paginated per-file outcomes for a download job."""

    job_id: str = Field(..., description="UUID of the download job.")
    total: int = Field(..., description="Total items matching the filter.")
    limit: int = Field(..., description="Page size.")
    offset: int = Field(..., description="Page offset.")
    items: List[DownloadJobItem] = Field(..., description="Page of items.")


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


async def _record_job_items(job_id: uuid.UUID, items: list):
    """Persist per-file outcomes for a download job."""
    if not items:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO download_job_items "
            "(job_id, doc_id, file_path, status, detail) "
            "VALUES ($1, $2, $3, $4, $5)",
            [
                (
                    job_id,
                    item.get("doc_id"),
                    item.get("file_path"),
                    item.get("status"),
                    item.get("detail"),
                )
                for item in items
            ],
        )


async def _get_item_counts(job_id: uuid.UUID) -> dict:
    """Return per-status counts for a job's items."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS count FROM download_job_items "
            "WHERE job_id = $1 GROUP BY status",
            job_id,
        )
    return {row["status"]: row["count"] for row in rows}


def _busy_exception(active: asyncpg.Record) -> HTTPException:
    """Build a 409 response describing the download job that is already running."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "A download job is already running "
            f"(job_id={active['job_id']}, status={active['status']}, "
            f"chamber={active['chamber']}). Wait for it to complete before "
            "triggering another job to avoid overlapping downloads."
        ),
    )


async def _get_active_job() -> Optional[asyncpg.Record]:
    """Return the currently active download job, if any.

    Used as a cheap pre-check so an obviously-busy system rejects a trigger
    before the (potentially slow) candidate scan runs.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT job_id, status, chamber, created_at, updated_at "
            "FROM jobs WHERE status IN ('PENDING', 'IN_PROGRESS') "
            "ORDER BY created_at DESC LIMIT 1"
        )


async def _create_job_if_idle(
    job_id: uuid.UUID,
    *,
    chamber: Optional[str],
    requested_by: Optional[str],
) -> Optional[asyncpg.Record]:
    """Atomically insert a new download job iff no job is currently active.

    A transaction-scoped advisory lock serializes concurrent triggers so two
    callers cannot both pass the "system is idle" check and start overlapping
    runs. Stale jobs (no progress for ``STALE_JOB_HOURS``) are reaped first so a
    crashed run cannot block triggers forever.

    Returns the conflicting active job row when the system is busy, or ``None``
    when the new job was inserted successfully.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock($1)", _TRIGGER_ADVISORY_LOCK
            )
            if STALE_JOB_HOURS > 0:
                reaped = await conn.execute(
                    "UPDATE jobs SET status = 'FAILED', updated_at = NOW(), "
                    "error_message = COALESCE(error_message, 'Reaped: job stalled "
                    "without progress') "
                    "WHERE status IN ('PENDING', 'IN_PROGRESS') "
                    "AND updated_at < NOW() - $1::interval",
                    f"{STALE_JOB_HOURS} hours",
                )
                try:
                    reaped_count = int(reaped.split()[-1])
                except (ValueError, IndexError):
                    reaped_count = 0
                if reaped_count:
                    logger.warning("Reaped %d stale download job(s)", reaped_count)
            active = await conn.fetchrow(
                "SELECT job_id, status, chamber, created_at, updated_at "
                "FROM jobs WHERE status IN ('PENDING', 'IN_PROGRESS') "
                "ORDER BY created_at DESC LIMIT 1"
            )
            if active is not None:
                return active
            await conn.execute(
                "INSERT INTO jobs (job_id, status, chamber, requested_by) "
                "VALUES ($1, $2, $3, $4)",
                job_id,
                "IN_PROGRESS",
                chamber,
                requested_by,
            )
    return None


async def _execute_async_download(job_id: uuid.UUID, plans: list):
    """Background worker that downloads the pre-built queue for each chamber."""
    logger.info(
        "Job %s [download] started: %d chamber plan(s)", job_id, len(plans)
    )
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        total_downloaded = 0
        total_skipped = 0
        total_failed = 0
        for plan in plans:
            # Refresh updated_at so a long multi-chamber run is not mistaken for
            # a stalled job by the stale-job reaper.
            await _update_job_status(job_id, "IN_PROGRESS")
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
            stats = await asyncio.to_thread(
                download_filings.process_download_queue,
                queue,
                plan["base_output_dir"],
                plan["cfg"]["YEAR"],
                plan["cfg"],
            )
            total_downloaded += stats.get("DOWNLOADED", 0)
            total_skipped += stats.get("SKIPPED", 0)
            total_failed += stats.get("FAILED", 0)
            await _record_job_items(job_id, stats.get("items", []))
            logger.info(
                "Job %s [download] %s pipeline finished: "
                "downloaded=%d skipped=%d failed=%d",
                job_id, plan["cfg"]["CHAMBER"],
                stats.get("DOWNLOADED", 0),
                stats.get("SKIPPED", 0),
                stats.get("FAILED", 0),
            )

        attempted = total_downloaded + total_skipped + total_failed
        if attempted > 0 and total_downloaded == 0 and total_skipped == 0:
            # Every queued filing failed (e.g. the output volume is not
            # writable) → surface the job as FAILED with a clear hint.
            summary = (
                f"All {total_failed} queued filing(s) failed. Check that the "
                "output volume is writable by UID 10001 "
                "(e.g. `sudo chown -R 10001:10001 <host folder>`)."
            )
            await _update_job_status(job_id, "FAILED", summary)
            logger.error("Job %s [download] failed: %s", job_id, summary)
        elif total_failed > 0:
            summary = (
                f"{total_failed} failed, {total_downloaded} downloaded, "
                f"{total_skipped} skipped."
            )
            await _update_job_status(job_id, "COMPLETED", summary)
            logger.warning(
                "Job %s [download] completed with failures: %s", job_id, summary
            )
        else:
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
        409: {"description": "A download job is already running."},
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
    and how many were queued. ``limit`` caps the number of **new** downloads
    **per chamber**; with ``chamber="all"`` it applies independently to House and
    Senate (e.g. ``limit=5`` queues up to 5 House AND up to 5 Senate filings).
    ``0`` means "process all unprocessed candidates".
    """
    if request.chamber not in ("house", "senate", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: house, senate, all",
        )

    # ``limit`` is the canonical field; ``max_downloads`` is a backward-compatible
    # alias. Both default to 0, so use whichever is non-zero (0 = "all").
    limit = request.limit or request.max_downloads or 0
    force = bool(request.force or request.force_download)

    job_id = uuid.uuid4()
    logger.info(
        "Received download trigger: job=%s chamber=%s year=%s limit=%s "
        "force=%s requested_by=%s",
        job_id, request.chamber, request.year, limit,
        force, payload.get("sub"),
    )

    # Fast-fail if a job is already running so we do not waste an expensive
    # candidate scan on a trigger that will be rejected anyway. The atomic
    # guard below re-checks under an advisory lock to close the race window.
    active = await _get_active_job()
    if active is not None:
        raise _busy_exception(active)

    # Build the queue(s) synchronously so the response can report scan counters.
    # ``limit`` is applied PER CHAMBER: with chamber="all" and limit=5 the job
    # queues up to 5 House AND up to 5 Senate filings (10 total), rather than
    # splitting a single shared budget of 5 across both chambers.
    chambers = ["house", "senate"] if request.chamber == "all" else [request.chamber]
    plans = []
    total_candidates_scanned = 0
    skipped_already_downloaded = 0
    queued_for_download = 0
    try:
        for ch in chambers:
            env_file = ".env.house" if ch == "house" else ".env.senate"
            plan = await asyncio.to_thread(
                download_filings.build_download_queue,
                chamber=ch,
                env_file_path=env_file,
                year=request.year,
                max_downloads=limit,
                force_download=force,
            )
            plans.append(plan)
            total_candidates_scanned += plan["total_candidates_scanned"]
            skipped_already_downloaded += plan["skipped_already_downloaded"]
            queued_for_download += plan["queued_for_download"]
    except Exception as exc:
        logger.error("Job %s [download] queue build failed: %s", job_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to build download queue: {exc}",
        )

    conflict = await _create_job_if_idle(
        job_id,
        chamber=request.chamber,
        requested_by=payload.get("sub"),
    )
    if conflict is not None:
        raise _busy_exception(conflict)

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
    counts = await _get_item_counts(job_uuid)
    return {
        "job_id": str(job["job_id"]),
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "error_message": job["error_message"],
        "succeeded": counts.get("SUCCESS", 0),
        "skipped": counts.get("SKIPPED", 0),
        "failed": counts.get("FAILED", 0),
    }


@app.get(
    "/api/v1/download/status/{job_id}/items",
    response_model=DownloadJobItemsResponse,
    summary="List per-file outcomes for a download job",
    response_description="Paginated per-file results (success, skipped, failed).",
    tags=["Async Download"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Job not found."},
    },
)
async def get_download_job_items(
    job_id: str,
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by outcome: SUCCESS, SKIPPED, or FAILED.",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    payload: dict = Depends(require_role(["admin", "user"])),
):
    """Return paginated per-file outcomes for a download job.

    Allowed for the ``admin`` and ``user`` roles. Use ``status`` to filter to
    ``SUCCESS``, ``SKIPPED``, or ``FAILED``.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM jobs WHERE job_id = $1", job_uuid
        )
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        where = "WHERE job_id = $1"
        params = [job_uuid]
        if status_filter:
            where += " AND status = $2"
            params.append(status_filter.upper())
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM download_job_items {where}", *params
        )
        rows = await conn.fetch(
            f"SELECT doc_id, file_path, status, detail, created_at "
            f"FROM download_job_items {where} "
            f"ORDER BY id LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params,
            limit,
            offset,
        )
    return {
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
                "created_at": (
                    row["created_at"].isoformat() if row["created_at"] else None
                ),
            }
            for row in rows
        ],
    }
