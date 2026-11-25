#!/usr/bin/env python3
"""
Vectorizer & pgvector Ingestion Microservice API

FastAPI microservice that consumes the standardized JSON documents produced by
the Parser Service (``/data/parsed_json/{doc_id}.json``), converts each
disclosure item into a rich semantic text block, generates vector embeddings via
the **LiteLLM Proxy** container, and stores both relational metadata and the
embeddings in PostgreSQL (``congress-db``) using **pgvector**.

The service provides asynchronous, PostgreSQL-backed job tracking and
JWT-protected, role-gated endpoints.
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Dict, List, Optional

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

import chunker
import db_init
import embedder
from auth_utils import require_role, set_pool

# A dedicated "vectorizer" logger with its own handler so our INFO/DEBUG lines
# always appear in `docker logs` regardless of uvicorn's logging configuration.
logger = logging.getLogger("vectorizer")
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
# cannot both observe an idle system and start overlapping vectorization runs
# (which would overload the embedding backend).
_TRIGGER_ADVISORY_LOCK = 0x56454354  # "VECT"

# A PENDING/IN_PROGRESS job whose row has not been updated for this many hours is
# considered stale (e.g. the container was killed mid-run) and is reaped so it
# cannot block every future trigger forever. Set to 0 to disable reaping.
STALE_JOB_HOURS = float(os.getenv("VECTORIZER_STALE_JOB_HOURS", "2"))

# How often (seconds) the background reaper scans for stalled jobs. It runs
# independently of triggers so a crashed/killed job is always driven to a
# terminal state even if nobody re-triggers the pipeline.
STALE_CHECK_SECONDS = float(os.getenv("VECTORIZER_STALE_CHECK_SECONDS", "300"))

# How often (seconds) a running job refreshes ``updated_at`` while a single
# embedding call is in flight, so it is not mistaken for stalled.
HEARTBEAT_SECONDS = float(os.getenv("VECTORIZER_HEARTBEAT_SECONDS", "300"))

# How often (seconds) a running bulk job polls the ``cancel_requested`` flag so
# an admin-initiated cancellation is honoured at the next document boundary.
CANCEL_POLL_SECONDS = float(os.getenv("VECTORIZER_CANCEL_POLL_SECONDS", "5"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and initialize the schema on startup.

    The ``vector`` extension must exist before the asyncpg vector codec can be
    registered, so a short-lived connection enables the extension first, then the
    pool is created with the codec ``init`` callback, and finally the tables and
    indexes are created.
    """
    global pool
    bootstrap = await asyncpg.connect(DATABASE_URL)
    try:
        await db_init.ensure_vector_extension(bootstrap)
    finally:
        await bootstrap.close()

    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=10,
        init=db_init.register_vector_codec,
    )
    # Enable DB-backed authorization checks for downstream RBAC dependencies.
    set_pool(pool)
    await db_init.init_db(pool)
    # Run a periodic reaper so interrupted jobs reach a terminal state even when
    # no new trigger arrives (the trigger-time reaper alone would leave them
    # stuck in IN_PROGRESS forever).
    reaper_task: Optional[asyncio.Task] = None
    if STALE_JOB_HOURS > 0:
        reaper_task = asyncio.create_task(_reaper_loop())
    try:
        yield
    finally:
        if reaper_task is not None:
            reaper_task.cancel()
            try:
                await reaper_task
            except asyncio.CancelledError:
                pass
        await pool.close()


app = FastAPI(
    title="Congressional Disclosure Vectorizer Microservice",
    description=(
        "Microservice that turns the standardized JSON produced by the Parser "
        "Service into semantic text chunks, generates vector embeddings through "
        "a LiteLLM Proxy (OpenAI-compatible embeddings endpoint), and stores "
        "both relational metadata and 1536-d vectors in PostgreSQL using "
        "pgvector (HNSW cosine index).\n\n"
        "### Trigger modes\n"
        "`POST /api/v1/vectorize/trigger` vectorizes a single document; "
        "`POST /api/v1/vectorize/trigger-bulk` scans `/data/parsed_json/` and "
        "vectorizes un-vectorized documents for the selected chamber(s). Use "
        "`limit` to cap the number of **new/unvectorized** documents queued "
        "(already-vectorized documents are skipped and do not count toward the "
        "limit; `limit: 0` processes all unvectorized documents). Set "
        "`force_revectorize: true` to bypass deduplication.\n\n"
        "### Concurrency\n"
        "Only one vectorization job may run at a time. A trigger received while "
        "a job is `PENDING` or `IN_PROGRESS` is rejected with `409 Conflict` "
        "(the response names the running job), so the embedding backend is never "
        "overloaded by overlapping runs. A job that stalls without progress is "
        "reaped after `VECTORIZER_STALE_JOB_HOURS` so it cannot block future "
        "triggers forever.\n\n"
        "### Authorization\n"
        "All `/api/v1/vectorize/*` routes require a Bearer JWT. Triggering "
        "requires the `admin` role; status and document retrieval allow `admin` "
        "or `user`."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "General", "description": "Health and readiness probes."},
        {
            "name": "Vectorize",
            "description": (
                "Single and bulk vectorization jobs. Triggering requires the "
                "`admin` role; status/document retrieval allow `admin` or `user`."
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


# ==============================================================================
# REQUEST / RESPONSE MODELS
# ==============================================================================

class VectorizeRequest(BaseModel):
    """Request body for ``POST /api/v1/vectorize/trigger`` (single document)."""

    doc_id: str = Field(
        ...,
        description="Document ID of the parsed JSON to vectorize (e.g. '10073198').",
    )
    embedding_model: Optional[str] = Field(
        default=None,
        description=(
            "LiteLLM embedding model alias (default: 'text-embedding-3-small'). "
            "Must be routable by the LiteLLM Proxy."
        ),
    )
    force: Optional[bool] = Field(
        default=False,
        description=(
            "Re-vectorize a document even if embeddings already exist. When "
            "false, already-vectorized documents are skipped."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Vectorize a single document",
                    "value": {
                        "doc_id": "10073198",
                        "embedding_model": "text-embedding-3-small",
                        "force": False,
                    },
                }
            ]
        }
    )


class BulkVectorizeRequest(BaseModel):
    """Request body for ``POST /api/v1/vectorize/trigger-bulk``."""

    chamber: Optional[str] = Field(
        default="all",
        description="Chamber to process: 'house', 'senate', or 'all'.",
    )
    embedding_model: Optional[str] = Field(
        default=None,
        description=(
            "LiteLLM embedding model alias (default: 'text-embedding-3-small')."
        ),
    )
    force: Optional[bool] = Field(
        default=False,
        description=(
            "Deprecated alias for ``force_revectorize``. Re-vectorize documents "
            "even if embeddings already exist."
        ),
    )
    force_revectorize: Optional[bool] = Field(
        default=False,
        description=(
            "Re-vectorize documents even if embeddings already exist. When "
            "false, already-vectorized documents are skipped."
        ),
    )
    limit: Optional[int] = Field(
        default=0,
        description=(
            "Maximum number of NEW (unvectorized) documents to queue. "
            "Already-vectorized documents are skipped and do not count toward "
            "the limit. 0 = process all unvectorized documents."
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Bulk vectorize all chambers",
                    "value": {
                        "chamber": "all",
                        "embedding_model": "text-embedding-3-small",
                        "force_revectorize": False,
                        "limit": 0,
                    },
                },
                {
                    "summary": "Bulk vectorize Senate only, force re-vectorize",
                    "value": {
                        "chamber": "senate",
                        "force_revectorize": True,
                        "limit": 10,
                    },
                },
            ]
        }
    )


class VectorizeTriggerResponse(BaseModel):
    """Response returned by the trigger endpoints (202 Accepted)."""

    job_id: str = Field(..., description="UUID of the enqueued vectorization job.")
    status: str = Field(
        ..., description="Initial job status (IN_PROGRESS or PENDING)."
    )
    mode: str = Field(..., description="Processing mode: 'single' or 'bulk'.")
    total_jsons_scanned: Optional[int] = Field(
        default=None, description="Parsed JSON files inspected (bulk mode)."
    )
    skipped_already_vectorized: Optional[int] = Field(
        default=None, description="Documents skipped because embeddings exist."
    )
    queued_for_vectorization: Optional[int] = Field(
        default=None, description="Documents queued for embedding."
    )


class VectorizeStatusResponse(BaseModel):
    """Response returned by ``GET /api/v1/vectorize/status/{job_id}``."""

    job_id: str = Field(..., description="UUID of the vectorization job.")
    doc_id: Optional[str] = Field(default=None, description="Document ID (single mode).")
    chamber: Optional[str] = Field(default=None, description="Chamber or 'all' (bulk).")
    model: Optional[str] = Field(default=None, description="Embedding model alias used.")
    requested_by: Optional[str] = Field(
        default=None, description="Username that triggered the job."
    )
    mode: Optional[str] = Field(default=None, description="'single' or 'bulk'.")
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
            "embedding calls."
        ),
    )
    status: str = Field(..., description="PENDING, IN_PROGRESS, COMPLETED, or FAILED.")
    created_at: str = Field(..., description="Job creation timestamp (ISO 8601).")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601).")
    error_message: Optional[str] = Field(
        default=None,
        description="Error detail when FAILED, or a partial-failure/skip summary.",
    )
    succeeded: int = Field(
        default=0, description="Documents successfully vectorized (per-item count)."
    )
    skipped: int = Field(
        default=0, description="Documents skipped as already vectorized (per-item count)."
    )
    failed: int = Field(
        default=0, description="Documents that failed vectorization (per-item count)."
    )


class VectorizeJobItem(BaseModel):
    """A single per-document outcome within a vectorization job."""

    doc_id: Optional[str] = Field(default=None, description="Document ID.")
    file_path: Optional[str] = Field(
        default=None, description="Relative path on the /data volume."
    )
    status: str = Field(..., description="SUCCESS, SKIPPED, or FAILED.")
    detail: Optional[str] = Field(
        default=None, description="Error detail or skip reason."
    )
    cost: Optional[float] = Field(
        default=None, description="Embedding cost (USD) attributed to this document."
    )
    created_at: Optional[str] = Field(
        default=None, description="When the item was recorded (ISO 8601)."
    )


class VectorizeJobItemsResponse(BaseModel):
    """Paginated per-document outcomes for a vectorization job."""

    job_id: str = Field(..., description="UUID of the vectorization job.")
    total: int = Field(..., description="Items matching the filter.")
    limit: int = Field(..., description="Page size.")
    offset: int = Field(..., description="Page offset.")
    items: List[VectorizeJobItem] = Field(..., description="Page of items.")


# ==============================================================================
# JOB TRACKING HELPERS
# ==============================================================================

async def _update_job_status(
    job_id: uuid.UUID, status_value: str, error_message: Optional[str] = None
):
    """Update the status of a vectorization job in PostgreSQL."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE vectorizer_jobs SET status = $1, updated_at = NOW(), "
            "error_message = $2 WHERE job_id = $3",
            status_value,
            error_message,
            job_id,
        )


async def _set_job_totals(job_id: uuid.UUID, total_documents: int):
    """Record the total number of documents a bulk job will process."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE vectorizer_jobs SET total_documents = $1, updated_at = NOW() "
            "WHERE job_id = $2",
            total_documents,
            job_id,
        )


async def _update_job_progress(job_id: uuid.UUID, processed_documents: int):
    """Record how many documents a bulk job has processed so far."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE vectorizer_jobs SET processed_documents = $1, updated_at = NOW() "
            "WHERE job_id = $2",
            processed_documents,
            job_id,
        )


async def _set_job_cost(job_id: uuid.UUID, total_cost: float):
    """Record the total LiteLLM-reported cost (USD) for a job."""
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE vectorizer_jobs SET total_cost = $1, updated_at = NOW() "
            "WHERE job_id = $2",
            total_cost,
            job_id,
        )


async def _record_job_items(job_id: uuid.UUID, items: list):
    """Persist per-document outcomes for a vectorization job."""
    if not items:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO vectorizer_job_items "
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
    """Return per-status counts for a vectorization job's items."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT status, COUNT(*) AS count FROM vectorizer_job_items "
            "WHERE job_id = $1 GROUP BY status",
            job_id,
        )
    return {row["status"]: row["count"] for row in rows}


async def _is_cancel_requested(job_id: uuid.UUID) -> bool:
    """Return True when an admin has requested cancellation for this job."""
    async with pool.acquire() as conn:
        return bool(
            await conn.fetchval(
                "SELECT cancel_requested FROM vectorizer_jobs WHERE job_id = $1",
                job_id,
            )
        )


def _busy_exception(active: asyncpg.Record) -> HTTPException:
    """Build a 409 response describing the vectorization job already running."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "A vectorization job is already running "
            f"(job_id={active['job_id']}, status={active['status']}, "
            f"mode={active['mode']}). Wait for it to complete before triggering "
            "another job to avoid overloading the embedding backend."
        ),
    )


async def _get_active_job() -> Optional[asyncpg.Record]:
    """Return the currently active vectorization job, if any.

    Used as a cheap pre-check so an obviously-busy system rejects a trigger
    before the (potentially slow) parsed-JSON scan runs.
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT job_id, status, mode, chamber, doc_id, created_at, updated_at "
            "FROM vectorizer_jobs WHERE status IN ('PENDING', 'IN_PROGRESS') "
            "ORDER BY created_at DESC LIMIT 1"
        )


async def _create_job_if_idle(
    job_id: uuid.UUID,
    *,
    mode: str,
    doc_id: Optional[str],
    chamber: Optional[str],
    model: str,
    requested_by: Optional[str],
    total_documents: Optional[int],
    status_value: str,
) -> Optional[asyncpg.Record]:
    """Atomically insert a new vectorization job iff no job is currently active.

    A transaction-scoped advisory lock serializes concurrent triggers so two
    callers cannot both pass the "system is idle" check and start overlapping
    runs. Stale jobs (no progress for ``STALE_JOB_HOURS``) are reaped first so a
    crashed run cannot block triggers forever.

    Returns the conflicting active job row when the system is busy, or ``None``
    when the new job was inserted successfully.
    """
    # Drive any orphaned/stalled jobs to a truthful terminal state first so they
    # do not block this trigger.
    await _reconcile_stale_jobs()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock($1)", _TRIGGER_ADVISORY_LOCK
            )
            active = await conn.fetchrow(
                "SELECT job_id, status, mode, chamber, doc_id, created_at, updated_at "
                "FROM vectorizer_jobs WHERE status IN ('PENDING', 'IN_PROGRESS') "
                "ORDER BY created_at DESC LIMIT 1"
            )
            if active is not None:
                return active
            await conn.execute(
                "INSERT INTO vectorizer_jobs "
                "(job_id, mode, doc_id, chamber, model, requested_by, "
                "total_documents, status) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                job_id,
                mode,
                doc_id,
                chamber,
                model,
                requested_by,
                total_documents,
                status_value,
            )
    return None


# ==============================================================================
# BACKGROUND WORKERS
# ==============================================================================

async def _run_with_heartbeat(job_id: uuid.UUID, coro_factory):
    """Await ``coro_factory()`` while refreshing ``updated_at`` in the background.

    A slow embedding call can exceed the stale-job threshold. Without an
    in-flight heartbeat the reaper would mistake a healthy run for a stalled one
    and finalise it prematurely.
    """
    stop = asyncio.Event()

    async def _beat() -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
                return
            except asyncio.TimeoutError:
                try:
                    await _update_job_status(job_id, "IN_PROGRESS")
                except Exception:  # pragma: no cover - best effort
                    logger.debug("Heartbeat update failed for job %s", job_id)

    beat_task = asyncio.create_task(_beat())
    try:
        return await coro_factory()
    finally:
        stop.set()
        beat_task.cancel()
        try:
            await beat_task
        except (asyncio.CancelledError, Exception):
            pass


async def _reconcile_stale_jobs() -> int:
    """Finalise stalled PENDING/IN_PROGRESS jobs based on their progress.

    A job interrupted by a container restart never writes its own terminal
    status, so it would otherwise sit in ``IN_PROGRESS`` forever. This chooses a
    truthful terminal status: ``COMPLETED`` when every queued document was
    processed (or the recorded items prove the work landed), otherwise
    ``FAILED``. Returns the number of rows finalised.
    """
    if STALE_JOB_HOURS <= 0:
        return 0
    finalised = 0
    async with pool.acquire() as conn:
        stale = await conn.fetch(
            "SELECT job_id, total_documents, processed_documents "
            "FROM vectorizer_jobs "
            "WHERE status IN ('PENDING', 'IN_PROGRESS') "
            "AND updated_at < NOW() - $1::interval",
            timedelta(hours=STALE_JOB_HOURS),
        )
        for row in stale:
            job_id = row["job_id"]
            total = row["total_documents"]
            processed = row["processed_documents"] or 0
            counts = await conn.fetch(
                "SELECT status, COUNT(*) AS count FROM vectorizer_job_items "
                "WHERE job_id = $1 GROUP BY status",
                job_id,
            )
            done_items = sum(
                int(r["count"])
                for r in counts
                if r["status"] in ("SUCCESS", "SKIPPED", "FAILED")
            )
            if total is not None and int(total) == 0:
                status_value = "COMPLETED"
                message = "Reconciled after interruption: nothing was queued."
            elif total is not None and processed >= int(total):
                status_value = "COMPLETED"
                message = (
                    "Reconciled after interruption: all "
                    f"{total} document(s) were processed."
                )
            elif total is None and done_items > 0:
                status_value = "COMPLETED"
                message = "Reconciled after interruption: embedding result recorded."
            else:
                status_value = "FAILED"
                total_s = "?" if total is None else str(total)
                message = (
                    "Reaped: job stalled/interrupted before completing "
                    f"({processed}/{total_s} document(s) processed)."
                )
            result = await conn.execute(
                "UPDATE vectorizer_jobs SET status = $1, updated_at = NOW(), "
                "error_message = $2 "
                "WHERE job_id = $3 AND status IN ('PENDING', 'IN_PROGRESS')",
                status_value,
                message,
                job_id,
            )
            try:
                finalised += int(result.split()[-1])
            except (ValueError, IndexError):
                pass
    if finalised:
        logger.warning("Reconciled %d stale vectorization job(s)", finalised)
    return finalised


async def _reaper_loop() -> None:
    """Periodically finalise stalled jobs so the DB never stays IN_PROGRESS."""
    while True:
        try:
            await asyncio.sleep(STALE_CHECK_SECONDS)
            await _reconcile_stale_jobs()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Periodic vectorization-job reaper failed: %s", exc)


async def _execute_single_job(
    job_id: uuid.UUID,
    doc_id: str,
    model: Optional[str],
    force: bool,
):
    """Background worker that vectorizes a single document."""
    logger.info(
        "Job %s [single] started: doc_id=%s model=%s force=%s",
        job_id, doc_id, model or embedder.DEFAULT_EMBEDDING_MODEL, force,
    )
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        result = await _run_with_heartbeat(
            job_id,
            lambda: embedder.vectorize_document(
                pool, doc_id, model=model, force=force
            ),
        )
        note = None
        if result["status"] == "SKIPPED_ALREADY_VECTORIZED":
            note = "Skipped: already vectorized (set force=true to re-vectorize)"
        elif result["status"] == "NO_ITEMS":
            note = "No disclosure items to vectorize"
        await _set_job_cost(job_id, result.get("cost", 0.0))
        await _record_job_items(
            job_id,
            [
                {
                    "doc_id": doc_id,
                    "file_path": None,
                    "status": (
                        "SKIPPED"
                        if result["status"] == "SKIPPED_ALREADY_VECTORIZED"
                        else "SUCCESS"
                    ),
                    "detail": note,
                    "cost": result.get("cost", 0.0),
                }
            ],
        )
        await _update_job_status(job_id, "COMPLETED", note)
        logger.info(
            "Job %s [single] completed: doc_id=%s status=%s items=%d cost=$%.6f",
            job_id, doc_id, result["status"], result["items"],
            result.get("cost", 0.0),
        )
    except Exception as exc:
        await _record_job_items(
            job_id,
            [
                {
                    "doc_id": doc_id,
                    "file_path": None,
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
    force: bool,
):
    """Background worker that vectorizes the pre-built queue of documents.

    ``documents`` is the queue selected by the trigger endpoint (already filtered
    to unvectorized items and capped by ``limit``). Documents are processed
    sequentially; progress is written to PostgreSQL after each one so the status
    endpoint can report ``processed_documents`` / ``total_documents``.
    """
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        await _set_job_totals(job_id, len(documents))
        total = len(documents)
        logger.info(
            "Job %s [bulk] started: chamber=%s model=%s documents=%d force=%s",
            job_id, chamber or "all", model or embedder.DEFAULT_EMBEDDING_MODEL,
            total, force,
        )

        processed = 0
        succeeded = 0
        skipped = 0
        total_cost = 0.0
        failures: List[str] = []
        cancelled = False

        for index, doc in enumerate(documents, start=1):
            # Cooperative cancellation: stop at the next document boundary when
            # the admin has requested cancellation for this job.
            if await _is_cancel_requested(job_id):
                cancelled = True
                logger.warning(
                    "Job %s [bulk] cancellation requested; stopping after "
                    "%d/%d document(s).", job_id, processed, total,
                )
                break
            doc_id = doc["doc_id"]
            file_path = doc.get("file_path")
            # Skip documents whose embeddings already exist (unless forced).
            if not force and await embedder.is_already_vectorized(pool, doc_id):
                logger.info(
                    "[%d/%d] SKIPPED_ALREADY_VECTORIZED doc_id=%s",
                    index, total, doc_id,
                )
                skipped += 1
                processed += 1
                await _record_job_items(
                    job_id,
                    [
                        {
                            "doc_id": doc_id,
                            "file_path": file_path,
                            "status": "SKIPPED",
                            "detail": "already vectorized",
                        }
                    ],
                )
                await _update_job_progress(job_id, processed)
                continue
            try:
                result = await _run_with_heartbeat(
                    job_id,
                    lambda: embedder.vectorize_document(
                        pool, doc_id, model=model, force=force
                    ),
                )
                total_cost += result.get("cost", 0.0)
                if result["status"] == "SKIPPED_ALREADY_VECTORIZED":
                    skipped += 1
                    item_status = "SKIPPED"
                    item_detail = "already vectorized"
                else:
                    succeeded += 1
                    item_status = "SUCCESS"
                    item_detail = None
                await _record_job_items(
                    job_id,
                    [
                        {
                            "doc_id": doc_id,
                            "file_path": file_path,
                            "status": item_status,
                            "detail": item_detail,
                            "cost": result.get("cost", 0.0),
                        }
                    ],
                )
                logger.info(
                    "[%d/%d] OK doc_id=%s status=%s items=%d cost=$%.6f",
                    index, total, doc_id, result["status"], result["items"],
                    result.get("cost", 0.0),
                )
            except Exception as exc:  # keep going; record the failure
                failures.append(f"{doc_id}: {exc}")
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
                logger.error(
                    "[%d/%d] FAIL doc_id=%s error=%s", index, total, doc_id, exc
                )
            processed += 1
            await _update_job_progress(job_id, processed)

        await _set_job_cost(job_id, total_cost)
        logger.info(
            "Job %s [bulk] finished: vectorized=%d skipped=%d failed=%d cost=$%.6f",
            job_id, succeeded, skipped, len(failures), total_cost,
        )

        if cancelled:
            summary = (
                f"Cancelled by admin after {processed}/{total} document(s) "
                f"({succeeded} vectorized, {skipped} skipped, "
                f"{len(failures)} failed)."
            )
            await _update_job_status(job_id, "CANCELLED", summary)
            logger.warning("Job %s [bulk] cancelled: %s", job_id, summary)
            return

        # Every attempted document failed → surface the job as FAILED.
        if failures and succeeded == 0 and skipped == 0:
            summary = f"All {len(failures)} document(s) failed: " + "; ".join(failures[:10])
            await _update_job_status(job_id, "FAILED", summary)
        elif failures:
            summary = (
                f"{len(failures)} failed, {succeeded} vectorized, {skipped} skipped: "
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


@app.post(
    "/api/v1/vectorize/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VectorizeTriggerResponse,
    summary="Trigger a single-document vectorization job",
    response_description="The job was accepted and enqueued for background processing.",
    tags=["Vectorize"],
    responses={
        400: {"description": "Invalid doc_id (absolute path or traversal)."},
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' role."},
        404: {"description": "Parsed document not found."},
        409: {"description": "A vectorization job is already running."},
    },
)
async def trigger_vectorize(
    background_tasks: BackgroundTasks,
    request: VectorizeRequest = Body(
        ...,
        openapi_examples={
            "single_document": {
                "summary": "Vectorize a single document",
                "value": {
                    "doc_id": "10073198",
                    "embedding_model": "text-embedding-3-small",
                    "force": False,
                },
            }
        },
    ),
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Trigger a single-document vectorization job asynchronously.

    Requires the ``admin`` role. Validates that
    ``/data/parsed_json/{doc_id}.json`` exists, then enqueues a background task
    and returns a job ID immediately.
    """
    requested_by = payload.get("sub")
    model = request.embedding_model or embedder.DEFAULT_EMBEDDING_MODEL

    # Reject absolute paths / traversal before touching the filesystem.
    if not chunker.is_valid_doc_id(request.doc_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid doc_id",
        )
    if not chunker.parsed_document_exists(request.doc_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        )

    job_id = uuid.uuid4()
    logger.info(
        "Received vectorize trigger: job=%s mode=single doc_id=%s model=%s "
        "force=%s requested_by=%s",
        job_id, request.doc_id, model, request.force, requested_by,
    )

    conflict = await _create_job_if_idle(
        job_id,
        mode="single",
        doc_id=request.doc_id,
        chamber=None,
        model=model,
        requested_by=requested_by,
        total_documents=1,
        status_value="PENDING",
    )
    if conflict is not None:
        raise _busy_exception(conflict)

    background_tasks.add_task(
        _execute_single_job,
        job_id,
        request.doc_id,
        request.embedding_model,
        request.force or False,
    )
    return {"job_id": str(job_id), "status": "PENDING", "mode": "single"}


@app.post(
    "/api/v1/vectorize/trigger-bulk",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=VectorizeTriggerResponse,
    summary="Trigger a bulk vectorization job",
    response_description="The job was accepted and enqueued for background processing.",
    tags=["Vectorize"],
    responses={
        400: {"description": "Invalid chamber value."},
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' role."},
        409: {"description": "A vectorization job is already running."},
    },
)
async def trigger_vectorize_bulk(
    background_tasks: BackgroundTasks,
    request: BulkVectorizeRequest = Body(
        ...,
        openapi_examples={
            "bulk_all": {
                "summary": "Bulk vectorize all chambers",
                "value": {
                    "chamber": "all",
                    "embedding_model": "text-embedding-3-small",
                    "force_revectorize": False,
                    "limit": 0,
                },
            },
            "bulk_senate_force": {
                "summary": "Bulk vectorize Senate only, force re-vectorize",
                "value": {
                    "chamber": "senate",
                    "force_revectorize": True,
                    "limit": 10,
                },
            },
        },
    ),
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Trigger a bulk vectorization job asynchronously.

    Requires the ``admin`` role. Scans ``/data/parsed_json/`` for parsed documents
    matching the requested chamber, selects up to ``limit`` *unvectorized*
    documents (already-vectorized ones are skipped unless ``force_revectorize`` is
    true), queues them, and returns a job ID immediately with scan counters.
    """
    requested_by = payload.get("sub")
    model = request.embedding_model or embedder.DEFAULT_EMBEDDING_MODEL

    chamber = (request.chamber or "all").lower()
    if chamber not in ("house", "senate", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: house, senate, all",
        )

    force = bool(request.force_revectorize or request.force)
    limit = request.limit or 0

    job_id = uuid.uuid4()
    logger.info(
        "Received vectorize trigger: job=%s mode=bulk chamber=%s model=%s "
        "force=%s limit=%s requested_by=%s",
        job_id, chamber, model, force, limit, requested_by,
    )

    # Fast-fail if a job is already running so we do not waste an expensive
    # parsed-JSON scan on a trigger that will be rejected anyway. The atomic
    # guard below re-checks under an advisory lock to close the race window.
    active = await _get_active_job()
    if active is not None:
        raise _busy_exception(active)

    # Scan parsed JSON files and select up to ``limit`` unvectorized documents.
    documents = await asyncio.to_thread(chunker.iter_parsed_documents, chamber)
    vectorized_ids = set() if force else await embedder.get_vectorized_doc_ids(pool)
    queue: List[Dict[str, str]] = []
    total_jsons_scanned = 0
    skipped_already_vectorized = 0
    for doc in documents:
        total_jsons_scanned += 1
        if not force and doc["doc_id"] in vectorized_ids:
            skipped_already_vectorized += 1
            continue
        queue.append(doc)
        if limit > 0 and len(queue) >= limit:
            break

    conflict = await _create_job_if_idle(
        job_id,
        mode="bulk",
        doc_id=None,
        chamber=chamber,
        model=model,
        requested_by=requested_by,
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
        request.embedding_model,
        force,
    )
    return {
        "job_id": str(job_id),
        "status": "IN_PROGRESS",
        "mode": "bulk",
        "total_jsons_scanned": total_jsons_scanned,
        "skipped_already_vectorized": skipped_already_vectorized,
        "queued_for_vectorization": len(queue),
    }


@app.get(
    "/api/v1/vectorize/status/{job_id}",
    response_model=VectorizeStatusResponse,
    summary="Get the status of a vectorization job",
    response_description="The current state of the job, including bulk progress counters.",
    tags=["Vectorize"],
    responses={
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Job not found."},
    },
)
async def get_vectorize_status(
    job_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return the current status of an asynchronous vectorization job.

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
            "FROM vectorizer_jobs WHERE job_id = $1",
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
    "/api/v1/vectorize/status/{job_id}/items",
    response_model=VectorizeJobItemsResponse,
    summary="List per-document outcomes for a vectorization job",
    response_description="Paginated per-document results (success, skipped, failed).",
    tags=["Vectorize"],
    responses={
        401: {"description": "Missing or JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
        404: {"description": "Job not found."},
    },
)
async def get_vectorize_job_items(
    job_id: str,
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by item status: SUCCESS, SKIPPED, or FAILED.",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Page size."),
    offset: int = Query(default=0, ge=0, description="Page offset."),
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return paginated per-document outcomes for a vectorization job.

    Allowed for the ``admin`` and ``user`` roles. Use ``status`` to filter to
    ``SUCCESS``, ``SKIPPED``, or ``FAILED`` items.
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
            "SELECT 1 FROM vectorizer_jobs WHERE job_id = $1", job_uuid
        )
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job not found",
            )
        where = "WHERE job_id = $1"
        params: List[Any] = [job_uuid]
        if status_filter:
            params.append(status_filter.upper())
            where += f" AND status = ${len(params)}"
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM vectorizer_job_items {where}", *params
        )
        rows = await conn.fetch(
            f"SELECT doc_id, file_path, status, detail, cost, created_at "
            f"FROM vectorizer_job_items {where} "
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
    "/api/v1/vectorize/document/{doc_id}",
    summary="Fetch the stored embedding metadata for a document",
    response_description="The stored chunk metadata (without raw vectors) for the document.",
    tags=["Vectorize"],
    responses={
        400: {"description": "Invalid doc_id (absolute path or traversal)."},
        401: {"description": "Missing or invalid JWT."},
        403: {"description": "Caller lacks the 'admin' or 'user' role."},
    },
)
async def get_document_embeddings(
    doc_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return the stored embedding metadata for a single document.

    Allowed for the ``admin`` and ``user`` roles. The raw vector is omitted to
    keep the response small; the semantic ``chunk_text`` is included.
    """
    if not chunker.is_valid_doc_id(doc_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid doc_id",
        )
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT item_index, chamber, filer_name, filing_date, report_type, "
            "contains_market_trades, is_market_trade, ticker, asset_name, "
            "asset_category, action, date, value_range, ownership, comment, "
            "chunk_text, created_at "
            "FROM disclosure_embeddings WHERE doc_id = $1 ORDER BY item_index",
            doc_id,
        )
    items = []
    for row in rows:
        items.append(
            {
                "item_index": row["item_index"],
                "chamber": row["chamber"],
                "filer_name": row["filer_name"],
                "filing_date": row["filing_date"].isoformat() if row["filing_date"] else None,
                "report_type": row["report_type"],
                "contains_market_trades": row["contains_market_trades"],
                "is_market_trade": row["is_market_trade"],
                "ticker": row["ticker"],
                "asset_name": row["asset_name"],
                "asset_category": row["asset_category"],
                "action": row["action"],
                "date": row["date"].isoformat() if row["date"] else None,
                "value_range": row["value_range"],
                "ownership": row["ownership"],
                "comment": row["comment"],
                "chunk_text": row["chunk_text"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
        )
    return {
        "doc_id": doc_id,
        "vectorized": bool(items),
        "item_count": len(items),
        "items": items,
    }
