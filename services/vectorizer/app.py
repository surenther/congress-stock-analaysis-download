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
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Request, status
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
    yield
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


# ==============================================================================
# BACKGROUND WORKERS
# ==============================================================================

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
        result = await embedder.vectorize_document(
            pool, doc_id, model=model, force=force
        )
        note = None
        if result["status"] == "SKIPPED_ALREADY_VECTORIZED":
            note = "Skipped: already vectorized (set force=true to re-vectorize)"
        elif result["status"] == "NO_ITEMS":
            note = "No disclosure items to vectorize"
        await _set_job_cost(job_id, result.get("cost", 0.0))
        await _update_job_status(job_id, "COMPLETED", note)
        logger.info(
            "Job %s [single] completed: doc_id=%s status=%s items=%d cost=$%.6f",
            job_id, doc_id, result["status"], result["items"],
            result.get("cost", 0.0),
        )
    except Exception as exc:
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

        for index, doc in enumerate(documents, start=1):
            doc_id = doc["doc_id"]
            # Skip documents whose embeddings already exist (unless forced).
            if not force and await embedder.is_already_vectorized(pool, doc_id):
                logger.info(
                    "[%d/%d] SKIPPED_ALREADY_VECTORIZED doc_id=%s",
                    index, total, doc_id,
                )
                skipped += 1
                processed += 1
                await _update_job_progress(job_id, processed)
                continue
            try:
                result = await embedder.vectorize_document(
                    pool, doc_id, model=model, force=force
                )
                total_cost += result.get("cost", 0.0)
                if result["status"] == "SKIPPED_ALREADY_VECTORIZED":
                    skipped += 1
                else:
                    succeeded += 1
                logger.info(
                    "[%d/%d] OK doc_id=%s status=%s items=%d cost=$%.6f",
                    index, total, doc_id, result["status"], result["items"],
                    result.get("cost", 0.0),
                )
            except Exception as exc:  # keep going; record the failure
                failures.append(f"{doc_id}: {exc}")
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

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO vectorizer_jobs "
            "(job_id, mode, doc_id, model, requested_by, total_documents, status) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            job_id,
            "single",
            request.doc_id,
            model,
            requested_by,
            1,
            "PENDING",
        )

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

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO vectorizer_jobs "
            "(job_id, mode, chamber, model, requested_by, total_documents, status) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            job_id,
            "bulk",
            chamber,
            model,
            requested_by,
            len(queue),
            "IN_PROGRESS",
        )

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
