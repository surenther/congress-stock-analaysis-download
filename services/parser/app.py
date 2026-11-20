#!/usr/bin/env python3
"""
Congressional Disclosure Extraction Microservice API

FastAPI microservice that extracts structured data from raw House PDF and Senate
HTML disclosures stored on the external ``/data`` volume. Extraction is performed
by an LLM reached through a dedicated **LiteLLM Proxy** container, which routes
requests to OpenRouter, Hugging Face, or a local Ollama/vLLM backend.

The service provides asynchronous, PostgreSQL-backed job tracking and
JWT-protected, role-gated endpoints.
"""

import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from pydantic import BaseModel, ConfigDict, Field

import extraction_engine
from auth_utils import require_role, set_pool

# The "parser" logger is configured (handler + level) in extraction_engine.
logger = logging.getLogger("parser")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL must be set (e.g. "
        "postgresql://user:password@db:5432/congress_db)."
    )

pool: Optional[asyncpg.Pool] = None

# Advisory-lock key used to serialize concurrent trigger requests so two callers
# cannot both observe an idle system and start overlapping parse runs (which
# would overload the LLM backend).
_TRIGGER_ADVISORY_LOCK = 0x50415253  # "PARS"

# A PENDING/IN_PROGRESS job whose row has not been updated for this many hours is
# considered stale (e.g. the container was killed mid-run) and is reaped so it
# cannot block every future trigger forever. Set to 0 to disable reaping.
STALE_JOB_HOURS = float(os.getenv("PARSER_STALE_JOB_HOURS", "2"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and initialize the parse_jobs table on startup."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    # Enable DB-backed authorization checks for downstream RBAC dependencies.
    set_pool(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parse_jobs (
                job_id UUID PRIMARY KEY,
                doc_id VARCHAR(255),
                chamber VARCHAR(20),
                model VARCHAR(100),
                requested_by VARCHAR(255),
                mode VARCHAR(20) NOT NULL DEFAULT 'single',
                total_documents INTEGER,
                processed_documents INTEGER NOT NULL DEFAULT 0,
                total_cost DOUBLE PRECISION NOT NULL DEFAULT 0,
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                error_message TEXT
            );
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'single';
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS total_documents INTEGER;
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS processed_documents INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS total_cost DOUBLE PRECISION NOT NULL DEFAULT 0;

            CREATE TABLE IF NOT EXISTS parse_job_items (
                id BIGSERIAL PRIMARY KEY,
                job_id UUID NOT NULL,
                doc_id VARCHAR(64),
                file_path TEXT,
                status VARCHAR(20) NOT NULL,
                detail TEXT,
                cost DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_parse_job_items_job
                ON parse_job_items (job_id, status);
            """
        )
    yield
    await pool.close()


app = FastAPI(
    title="Congressional Disclosure Extraction Microservice",
    description=(
        "Microservice that extracts structured data from U.S. House PDF and "
        "U.S. Senate HTML financial disclosure filings using an LLM routed "
        "through a LiteLLM Proxy (OpenRouter / Hugging Face / local Ollama). "
        "Output is standardized JSON (trades vs. non-trade disclosures) written "
        "to an external mounted volume.\n\n"
        "### Trigger modes\n"
        "`POST /api/v1/parse/trigger` supports two modes:\n\n"
        "* **Bulk mode** (default) — omit `file_path` to process documents "
        "discovered on the `/data` volume for the selected chamber(s). A minimal "
        "body such as `{}` triggers a full House + Senate run. Use `limit` to cap "
        "the number of **new/unprocessed** documents queued (already-parsed "
        "documents are skipped and do not count toward the limit; `limit: 0` "
        "processes all unprocessed documents). Set `force_reparse: true` to bypass "
        "deduplication.\n"
        "* **Single-document mode** — provide `file_path` (and optionally "
        "`doc_id` / `chamber`) to extract exactly one filing.\n\n"
        "### Concurrency\n"
        "Only one parse job may run at a time. A trigger received while a job is "
        "`PENDING` or `IN_PROGRESS` is rejected with `409 Conflict` (the response "
        "names the running job), so the LLM backend is never overloaded by "
        "overlapping runs. A job that stalls without progress is reaped after "
        "`PARSER_STALE_JOB_HOURS` so it cannot block future triggers forever.\n\n"
        "### Authorization\n"
        "All `/api/v1/parse/*` routes require a Bearer JWT. Triggering requires "
        "the `admin` role; status and document retrieval allow `admin` or `user`."
    ),
    version="2.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "General", "description": "Health and readiness probes."},
        {
            "name": "Parse",
            "description": (
                "Bulk and single-document extraction jobs. Triggering requires "
                "the `admin` role; status/document retrieval allow `admin` or `user`."
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


class ParseRequest(BaseModel):
    """Request body for ``POST /api/v1/parse/trigger``.

    Two modes are supported:

    * **Bulk mode** (default) — omit ``file_path`` to process every document
      discovered on the ``/data`` volume for the selected chamber(s). A minimal
      body such as ``{}`` (or ``{"chamber": "all"}``) triggers a full run.
    * **Single-document mode** — provide ``file_path`` (and optionally ``doc_id``
      / ``chamber``) to extract exactly one filing.
    """

    file_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to a single raw document, relative to the /data volume. When "
            "omitted, the service runs in bulk mode and processes every document "
            "found for the selected chamber(s)."
        ),
    )
    doc_id: Optional[str] = Field(
        default=None,
        description="Document ID (single mode). Derived from the filename if omitted.",
    )
    chamber: Optional[str] = Field(
        default=None,
        description=(
            "Chamber to process: 'house', 'senate', or 'all'. Defaults to 'all' "
            "in bulk mode; derived from the path in single mode."
        ),
    )
    model: Optional[str] = Field(
        default=None,
        description=(
            "Optional LiteLLM model provider name. 'openrouter-deepseek-flash' "
            "(cheap, default), 'openrouter-gemini-flash' (costly), 'hf-qwen', or "
            "'local-llm'. Defaults to the service default."
        ),
    )
    force: Optional[bool] = Field(
        default=False,
        description=(
            "Deprecated alias for 'force_reparse'. Reprocess a document even if "
            "its parsed JSON already exists."
        ),
    )
    force_reparse: Optional[bool] = Field(
        default=False,
        description=(
            "Reprocess documents even if their parsed JSON already exists. "
            "Applies to both bulk and single-document modes; by default already "
            "parsed documents are skipped."
        ),
    )
    limit: Optional[int] = Field(
        default=0,
        description=(
            "Maximum number of NEW/unprocessed documents to queue in bulk mode. "
            "Already-parsed documents are skipped and do not count toward the "
            "limit. 0 = process all unprocessed documents."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Bulk mode — process all House + Senate documents",
                    "description": "An empty body triggers a full run.",
                    "value": {},
                },
                {
                    "summary": "Bulk mode — Senate only, force reparse",
                    "value": {"chamber": "senate", "force_reparse": True, "limit": 10},
                },
                {
                    "summary": "Single-document mode",
                    "value": {
                        "doc_id": "10073198",
                        "chamber": "House",
                        "file_path": (
                            "house_rep/2026/01_January/Buckhout_Laurie/10073198.pdf"
                        ),
                        "model": "openrouter-deepseek-flash",
                    },
                },
            ]
        }
    )


class ParseTriggerResponse(BaseModel):
    """Response returned by ``POST /api/v1/parse/trigger`` (202 Accepted)."""

    job_id: str = Field(..., description="UUID of the enqueued parse job.")
    status: str = Field(
        ...,
        description=(
            "Initial job status (IN_PROGRESS, PENDING, or COMPLETED if skipped)."
        ),
    )
    mode: str = Field(..., description="Processing mode: 'bulk' or 'single'.")
    skipped: Optional[bool] = Field(
        default=False,
        description=(
            "True when the document was already parsed and extraction was skipped."
        ),
    )
    total_files_scanned: Optional[int] = Field(
        default=None, description="Raw files inspected during bulk queue selection."
    )
    skipped_already_parsed: Optional[int] = Field(
        default=None, description="Files skipped because parsed JSON already existed."
    )
    queued_for_parsing: Optional[int] = Field(
        default=None, description="Documents queued for extraction."
    )


class ParseStatusResponse(BaseModel):
    """Response returned by ``GET /api/v1/parse/status/{job_id}``."""

    job_id: str = Field(..., description="UUID of the parse job.")
    doc_id: Optional[str] = Field(default=None, description="Document ID (single mode).")
    chamber: Optional[str] = Field(default=None, description="Chamber or 'all' (bulk).")
    model: Optional[str] = Field(default=None, description="LiteLLM model alias used.")
    requested_by: Optional[str] = Field(
        default=None, description="Username that triggered the job."
    )
    mode: Optional[str] = Field(default=None, description="'bulk' or 'single'.")
    total_documents: Optional[int] = Field(
        default=None, description="Total documents to process (bulk mode)."
    )
    processed_documents: Optional[int] = Field(
        default=None, description="Documents processed so far (bulk mode)."
    )
    total_cost: Optional[float] = Field(
        default=None,
        description=(
            "Total LiteLLM-reported cost (USD) accumulated across the job's "
            "LLM calls."
        ),
    )
    status: str = Field(..., description="PENDING, IN_PROGRESS, COMPLETED, or FAILED.")
    created_at: str = Field(..., description="Job creation timestamp (ISO 8601).")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601).")
    error_message: Optional[str] = Field(
        default=None,
        description="Error detail when FAILED, or a partial-failure summary.",
    )
    succeeded: int = Field(
        default=0, description="Documents successfully parsed (per-item count)."
    )
    skipped: int = Field(
        default=0, description="Documents skipped as already parsed (per-item count)."
    )
    failed: int = Field(
        default=0, description="Documents that failed extraction (per-item count)."
    )


class ParseJobItem(BaseModel):
    """A single per-document outcome within a parse job."""

    doc_id: Optional[str] = Field(default=None, description="Document ID.")
    file_path: Optional[str] = Field(
        default=None, description="Relative path on the /data volume."
    )
    status: str = Field(..., description="SUCCESS, SKIPPED, or FAILED.")
    detail: Optional[str] = Field(
        default=None, description="Error detail or skip reason."
    )
    cost: Optional[float] = Field(
        default=None, description="LLM cost (USD) attributed to this document."
    )
    created_at: Optional[str] = Field(
        default=None, description="When the item was recorded (ISO 8601)."
    )


class ParseJobItemsResponse(BaseModel):
    """Paginated per-document outcomes for a parse job."""

    job_id: str = Field(..., description="UUID of the parse job.")
    total: int = Field(..., description="Items matching the filter.")
    limit: int = Field(..., description="Page size.")
    offset: int = Field(..., description="Page offset.")
    items: List[ParseJobItem] = Field(..., description="Page of items.")


async def _update_job_status(
    job_id: uuid.UUID, status_value: str, error_message: Optional[str] = None
):
    """Update the status of a parse job in PostgreSQL."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE parse_jobs SET status = $1, updated_at = NOW(), error_message = $2 "
            "WHERE job_id = $3",
            status_value,
            error_message,
            job_id,
        )


async def _set_job_totals(job_id: uuid.UUID, total_documents: int):
    """Record the total number of documents a bulk job will process."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE parse_jobs SET total_documents = $1, updated_at = NOW() WHERE job_id = $2",
            total_documents,
            job_id,
        )


async def _update_job_progress(job_id: uuid.UUID, processed_documents: int):
    """Record how many documents a bulk job has processed so far."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE parse_jobs SET processed_documents = $1, updated_at = NOW() WHERE job_id = $2",
            processed_documents,
            job_id,
        )


async def _set_job_cost(job_id: uuid.UUID, total_cost: float):
    """Record the total LiteLLM-reported cost (USD) for a job."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE parse_jobs SET total_cost = $1, updated_at = NOW() WHERE job_id = $2",
            total_cost,
            job_id,
        )


async def _record_job_items(job_id: uuid.UUID, items: list):
    """Persist per-document outcomes for a parse job."""
    if not items:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO parse_job_items "
            "(job_id, doc_id, file_path, status, detail, cost) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            [
                (
                    job_id,
                    item.get("doc_id"),
                    item.get("file_path"),
                    item.get("status"),
                    item.get("detail"),
                    item.get("cost", 0.0),
                )
                for item in items
            ],
        )


async def _get_item_counts(job_id: uuid.UUID) -> dict:
    """Return per-status counts for a parse job's items."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS count FROM parse_job_items "
            "WHERE job_id = $1 GROUP BY status",
            job_id,
        )
    return {row["status"]: row["count"] for row in rows}


def _busy_exception(active: asyncpg.Record) -> HTTPException:
    """Build a 409 response describing the parse job that is already running."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "A parse job is already running "
            f"(job_id={active['job_id']}, status={active['status']}, "
            f"mode={active['mode']}). Wait for it to complete before triggering "
            "another job to avoid overloading the LLM backend."
        ),
    )


def _select_bulk_queue(
    documents: List[Dict[str, str]], force: bool, limit: int
) -> Tuple[List[Dict[str, str]], int, int]:
    """Select up to ``limit`` unprocessed documents from ``documents``.

    Runs in a worker thread (it performs a filesystem existence check per file)
    so the event loop is never blocked while a large volume is scanned. Returns
    ``(queue, total_files_scanned, skipped_already_parsed)``.
    """
    queue: List[Dict[str, str]] = []
    total_files_scanned = 0
    skipped_already_parsed = 0
    for doc in documents:
        total_files_scanned += 1
        if not force and extraction_engine.is_already_parsed(doc["doc_id"]):
            skipped_already_parsed += 1
            continue
        queue.append(doc)
        if limit > 0 and len(queue) >= limit:
            break
    return queue, total_files_scanned, skipped_already_parsed


async def _create_job_if_idle(
    job_id: uuid.UUID,
    *,
    doc_id: Optional[str],
    chamber: Optional[str],
    model: str,
    requested_by: Optional[str],
    mode: str,
    total_documents: Optional[int],
    status_value: str,
    processed_documents: int = 0,
    error_message: Optional[str] = None,
) -> Optional[asyncpg.Record]:
    """Atomically insert a new parse job iff no job is currently active.

    A transaction-scoped advisory lock serializes concurrent triggers so two
    callers cannot both pass the "system is idle" check and start overlapping
    runs (which would overload the LLM backend). Stale jobs (no progress for
    ``STALE_JOB_HOURS``) are reaped first so a crashed run cannot block triggers
    forever.

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
                    "UPDATE parse_jobs SET status = 'FAILED', updated_at = NOW(), "
                    "error_message = COALESCE(error_message, 'Reaped: job stalled "
                    "without progress') "
                    "WHERE status IN ('PENDING', 'IN_PROGRESS') "
                    "AND updated_at < NOW() - $1::interval",
                    timedelta(hours=STALE_JOB_HOURS),
                )
                try:
                    reaped_count = int(reaped.split()[-1])
                except (ValueError, IndexError):
                    reaped_count = 0
                if reaped_count:
                    logger.warning("Reaped %d stale parse job(s)", reaped_count)
            active = await conn.fetchrow(
                "SELECT job_id, status, mode, chamber, doc_id, created_at, updated_at "
                "FROM parse_jobs WHERE status IN ('PENDING', 'IN_PROGRESS') "
                "ORDER BY created_at DESC LIMIT 1"
            )
            if active is not None:
                return active
            await conn.execute(
                "INSERT INTO parse_jobs "
                "(job_id, doc_id, chamber, model, requested_by, mode, "
                "total_documents, processed_documents, status, error_message) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
                job_id,
                doc_id,
                chamber,
                model,
                requested_by,
                mode,
                total_documents,
                processed_documents,
                status_value,
                error_message,
            )
    return None


async def _execute_single_job(
    job_id: uuid.UUID,
    doc_id: str,
    chamber: str,
    file_path: str,
    model: Optional[str],
    user_metadata: Dict[str, Any],
):
    """Background worker that extracts a single document in a thread."""
    logger.info(
        "Job %s [single] started: doc_id=%s chamber=%s model=%s",
        job_id, doc_id, chamber, model or extraction_engine.DEFAULT_MODEL,
    )
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        _, cost = await asyncio.to_thread(
            extraction_engine.extract_document,
            doc_id=doc_id,
            chamber=chamber,
            file_path=file_path,
            model=model,
            user_metadata=user_metadata,
        )
        await _set_job_cost(job_id, cost)
        await _record_job_items(
            job_id,
            [
                {
                    "doc_id": doc_id,
                    "file_path": file_path,
                    "status": "SUCCESS",
                    "detail": None,
                    "cost": cost,
                }
            ],
        )
        await _update_job_status(job_id, "COMPLETED")
        logger.info(
            "Job %s [single] completed: doc_id=%s cost=$%.6f", job_id, doc_id, cost
        )
    except Exception as exc:
        await _record_job_items(
            job_id,
            [
                {
                    "doc_id": doc_id,
                    "file_path": file_path,
                    "status": "FAILED",
                    "detail": str(exc),
                }
            ],
        )
        await _update_job_status(job_id, "FAILED", str(exc))
        logger.error("Job %s [single] failed: doc_id=%s error=%s", job_id, doc_id, exc)


async def _execute_bulk_job(
    job_id: uuid.UUID,
    chamber: Optional[str],
    documents: List[Dict[str, str]],
    model: Optional[str],
    user_metadata: Dict[str, Any],
    force: bool,
):
    """Background worker that extracts the pre-built queue of documents.

    ``documents`` is the queue selected by the trigger endpoint (already filtered
    for unprocessed items and capped at ``limit``). Progress is written to
    PostgreSQL after each document so the status endpoint can report
    ``processed_documents`` / ``total_documents``.
    """
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        await _set_job_totals(job_id, len(documents))
        total = len(documents)
        logger.info(
            "Job %s [bulk] started: chamber=%s model=%s documents=%d force=%s",
            job_id, chamber or "all", model or extraction_engine.DEFAULT_MODEL, total, force,
        )

        processed = 0
        succeeded = 0
        skipped = 0
        total_cost = 0.0
        failures: List[str] = []

        for index, doc in enumerate(documents, start=1):
            # Skip documents whose parsed JSON already exists (unless forced).
            if not force and extraction_engine.is_already_parsed(doc["doc_id"]):
                logger.info(
                    "[%d/%d] SKIP doc_id=%s (already parsed) file=%s",
                    index, total, doc["doc_id"], doc["file_path"],
                )
                skipped += 1
                processed += 1
                await _record_job_items(
                    job_id,
                    [
                        {
                            "doc_id": doc["doc_id"],
                            "file_path": doc["file_path"],
                            "status": "SKIPPED",
                            "detail": "already parsed",
                        }
                    ],
                )
                await _update_job_progress(job_id, processed)
                continue
            try:
                _, cost = await asyncio.to_thread(
                    extraction_engine.extract_document,
                    doc_id=doc["doc_id"],
                    chamber=doc["chamber"],
                    file_path=doc["file_path"],
                    model=model,
                    user_metadata=user_metadata,
                )
                total_cost += cost
                succeeded += 1
                await _record_job_items(
                    job_id,
                    [
                        {
                            "doc_id": doc["doc_id"],
                            "file_path": doc["file_path"],
                            "status": "SUCCESS",
                            "detail": None,
                            "cost": cost,
                        }
                    ],
                )
                logger.info(
                    "[%d/%d] OK doc_id=%s chamber=%s cost=$%.6f",
                    index, total, doc["doc_id"], doc["chamber"], cost,
                )
            except Exception as exc:  # keep going; record the failure
                failures.append(f"{doc['doc_id']}: {exc}")
                await _record_job_items(
                    job_id,
                    [
                        {
                            "doc_id": doc["doc_id"],
                            "file_path": doc["file_path"],
                            "status": "FAILED",
                            "detail": str(exc),
                        }
                    ],
                )
                logger.error(
                    "[%d/%d] FAIL doc_id=%s error=%s",
                    index, total, doc["doc_id"], exc,
                )
            processed += 1
            await _update_job_progress(job_id, processed)

        await _set_job_cost(job_id, total_cost)
        logger.info(
            "Job %s [bulk] finished: parsed=%d skipped=%d failed=%d cost=$%.6f",
            job_id, succeeded, skipped, len(failures), total_cost,
        )

        # Every attempted document failed → surface the job as FAILED.
        if failures and succeeded == 0 and skipped == 0:
            summary = f"All {len(failures)} document(s) failed: " + "; ".join(failures[:10])
            await _update_job_status(job_id, "FAILED", summary)
        elif failures:
            summary = (
                f"{len(failures)} failed, {succeeded} parsed, {skipped} skipped: "
                + "; ".join(failures[:10])
            )
            await _update_job_status(job_id, "COMPLETED", summary)
        else:
            await _update_job_status(job_id, "COMPLETED")
    except Exception as exc:
        await _update_job_status(job_id, "FAILED", str(exc))
        logger.error("Job %s [bulk] failed: %s", job_id, exc)


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
# PARSE JOB ENDPOINTS (PostgreSQL-backed, JWT-protected, RBAC-gated)
# ==============================================================================

@app.post(
    "/api/v1/parse/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ParseTriggerResponse,
    summary="Trigger a bulk or single-document extraction job",
    response_description="The job was accepted and enqueued for background processing.",
    tags=["Parse"],
    responses={
        400: {"description": "Invalid chamber value."},
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' role."},
        409: {"description": "A parse job is already running."},
    },
)
async def trigger_parse(
    background_tasks: BackgroundTasks,
    request: ParseRequest = Body(
        ...,
        openapi_examples={
            "bulk_all": {
                "summary": "Bulk mode — all House + Senate documents",
                "description": "An empty body triggers a full run.",
                "value": {},
            },
            "bulk_senate_force": {
                "summary": "Bulk mode — Senate only, force reparse",
                "value": {"chamber": "senate", "force_reparse": True, "limit": 10},
            },
            "single_document": {
                "summary": "Single-document mode",
                "value": {
                    "doc_id": "10073198",
                    "chamber": "House",
                    "file_path": (
                        "house_rep/2026/01_January/Buckhout_Laurie/10073198.pdf"
                    ),
                    "model": "openrouter-deepseek-flash",
                },
            },
        },
    ),
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Trigger an extraction job asynchronously and return a job ID immediately.

    Requires the ``admin`` role.

    * **Bulk mode** (no ``file_path``): processes every document discovered on the
      ``/data`` volume for the selected chamber(s). A minimal body such as ``{}``
      triggers a full House + Senate run.
    * **Single-document mode** (``file_path`` provided): extracts exactly one
      filing.

    In both modes, a document whose ``parsed_json/{doc_id}.json`` already exists
    (and is non-empty) is skipped unless ``force`` is true.
    """
    model = request.model or extraction_engine.DEFAULT_MODEL
    requested_by = payload.get("sub")
    # Forward caller metadata to the LiteLLM Proxy for audit logging.
    user_metadata = {
        "user": requested_by,
        "roles": payload.get("roles", []),
    }

    job_id = uuid.uuid4()
    logger.info(
        "Received parse trigger: job=%s mode=%s chamber=%s doc_id=%s file_path=%s "
        "model=%s force=%s requested_by=%s",
        job_id,
        "single" if request.file_path else "bulk",
        request.chamber,
        request.doc_id,
        request.file_path,
        model,
        request.force,
        requested_by,
    )

    if request.file_path:
        # ------------------------------------------------------------------
        # Single-document mode
        # ------------------------------------------------------------------
        doc_id = request.doc_id or Path(request.file_path).stem
        if not extraction_engine.is_valid_doc_id(doc_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid doc_id",
            )
        chamber = request.chamber or extraction_engine.chamber_label_from_path(
            request.file_path
        )
        if chamber.lower() not in ("house", "senate"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="chamber must be one of: House, Senate",
            )
        chamber = chamber.capitalize()

        # Skip re-processing a document that was already parsed (unless forced).
        if extraction_engine.is_already_parsed(doc_id) and not (
            request.force_reparse or request.force
        ):
            logger.info(
                "Job %s [single] SKIP doc_id=%s (already parsed) file=%s",
                job_id, doc_id, request.file_path,
            )
            conflict = await _create_job_if_idle(
                job_id,
                doc_id=doc_id,
                chamber=chamber,
                model=model,
                requested_by=requested_by,
                mode="single",
                total_documents=1,
                processed_documents=1,
                status_value="COMPLETED",
                error_message="Skipped: already parsed (set force=true to reparse)",
            )
            if conflict is not None:
                raise _busy_exception(conflict)
            return {
                "job_id": str(job_id),
                "status": "COMPLETED",
                "mode": "single",
                "skipped": True,
            }

        conflict = await _create_job_if_idle(
            job_id,
            doc_id=doc_id,
            chamber=chamber,
            model=model,
            requested_by=requested_by,
            mode="single",
            total_documents=1,
            status_value="PENDING",
        )
        if conflict is not None:
            raise _busy_exception(conflict)

        background_tasks.add_task(
            _execute_single_job,
            job_id,
            doc_id,
            chamber,
            request.file_path,
            request.model,
            user_metadata,
        )
        return {
            "job_id": str(job_id),
            "status": "PENDING",
            "mode": "single",
            "skipped": False,
        }

    # ----------------------------------------------------------------------
    # Bulk mode
    # ----------------------------------------------------------------------
    chamber = (request.chamber or "all").lower()
    if chamber not in ("house", "senate", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: house, senate, all",
        )

    force = bool(request.force_reparse or request.force)
    limit = request.limit or 0

    # Scan raw files and select up to ``limit`` unprocessed documents. Both the
    # filesystem walk and the per-file existence checks run in a worker thread so
    # the event loop is never blocked — the status endpoint stays responsive even
    # while a large volume is being scanned.
    documents = await asyncio.to_thread(extraction_engine.iter_documents, chamber)
    queue, total_files_scanned, skipped_already_parsed = await asyncio.to_thread(
        _select_bulk_queue, documents, force, limit
    )

    conflict = await _create_job_if_idle(
        job_id,
        doc_id=None,
        chamber=chamber,
        model=model,
        requested_by=requested_by,
        mode="bulk",
        total_documents=len(queue),
        status_value="IN_PROGRESS",
    )
    if conflict is not None:
        raise _busy_exception(conflict)

    background_tasks.add_task(
        _execute_bulk_job,
        job_id,
        chamber,
        queue,
        request.model,
        user_metadata,
        force,
    )
    return {
        "job_id": str(job_id),
        "status": "IN_PROGRESS",
        "mode": "bulk",
        "skipped": False,
        "total_files_scanned": total_files_scanned,
        "skipped_already_parsed": skipped_already_parsed,
        "queued_for_parsing": len(queue),
    }


@app.get(
    "/api/v1/parse/status/{job_id}",
    response_model=ParseStatusResponse,
    summary="Get the status of a parse job",
    response_description="The current state of the job, including bulk progress counters.",
    tags=["Parse"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Job not found."},
    },
)
async def get_parse_status(
    job_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return the current status of an asynchronous parse job.

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
            "SELECT job_id, doc_id, chamber, model, requested_by, mode, "
            "total_documents, processed_documents, total_cost, status, "
            "created_at, updated_at, error_message "
            "FROM parse_jobs WHERE job_id = $1",
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
        "doc_id": job["doc_id"],
        "chamber": job["chamber"],
        "model": job["model"],
        "requested_by": job["requested_by"],
        "mode": job["mode"],
        "total_documents": job["total_documents"],
        "processed_documents": job["processed_documents"],
        "total_cost": job["total_cost"],
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "error_message": job["error_message"],
        "succeeded": counts.get("SUCCESS", 0),
        "skipped": counts.get("SKIPPED", 0),
        "failed": counts.get("FAILED", 0),
    }


@app.get(
    "/api/v1/parse/status/{job_id}/items",
    response_model=ParseJobItemsResponse,
    summary="List per-document outcomes for a parse job",
    response_description="Paginated per-document results (success, skipped, failed).",
    tags=["Parse"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Job not found."},
    },
)
async def get_parse_job_items(
    job_id: str,
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by outcome: SUCCESS, SKIPPED, or FAILED.",
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return paginated per-document outcomes for a parse job.

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
        exists = await conn.fetchval(
            "SELECT 1 FROM parse_jobs WHERE job_id = $1", job_uuid
        )
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        where = "WHERE job_id = $1"
        params: List[Any] = [job_uuid]
        if status_filter:
            where += " AND status = $2"
            params.append(status_filter.upper())
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM parse_job_items {where}", *params
        )
        rows = await conn.fetch(
            f"SELECT doc_id, file_path, status, detail, cost, created_at "
            f"FROM parse_job_items {where} "
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
                "cost": row["cost"],
                "created_at": (
                    row["created_at"].isoformat() if row["created_at"] else None
                ),
            }
            for row in rows
        ],
    }


@app.get(
    "/api/v1/parse/document/{doc_id}",
    summary="Fetch the parsed JSON for a document",
    response_description="The standardized parsed JSON document.",
    tags=["Parse"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Parsed document not found."},
    },
)
async def get_parsed_document(
    doc_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return the standardized parsed JSON for a single filing by DocID."""
    if not extraction_engine.is_valid_doc_id(doc_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        )
    parsed_dir = extraction_engine.get_parsed_json_dir()
    output_path = parsed_dir / f"{doc_id}.json"
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        )
    with open(output_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
