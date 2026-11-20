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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import BackgroundTasks, Body, Depends, FastAPI, HTTPException, Request, status
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
                status VARCHAR(20) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                error_message TEXT
            );
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'single';
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS total_documents INTEGER;
            ALTER TABLE parse_jobs ADD COLUMN IF NOT EXISTS processed_documents INTEGER NOT NULL DEFAULT 0;
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
        "* **Bulk mode** (default) — omit `file_path` to process **every** "
        "document discovered on the `/data` volume for the selected chamber(s). "
        "A minimal body such as `{}` triggers a full House + Senate run.\n"
        "* **Single-document mode** — provide `file_path` (and optionally "
        "`doc_id` / `chamber`) to extract exactly one filing.\n\n"
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
            "Reprocess a document even if its parsed JSON already exists. "
            "Applies to both bulk and single-document modes; by default already "
            "parsed documents are skipped."
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
                    "value": {"chamber": "senate", "force": True},
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
        ..., description="Initial job status (PENDING, or COMPLETED if skipped)."
    )
    mode: str = Field(..., description="Processing mode: 'bulk' or 'single'.")
    skipped: Optional[bool] = Field(
        default=False,
        description=(
            "True when the document was already parsed and extraction was skipped."
        ),
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
    status: str = Field(..., description="PENDING, IN_PROGRESS, COMPLETED, or FAILED.")
    created_at: str = Field(..., description="Job creation timestamp (ISO 8601).")
    updated_at: str = Field(..., description="Last update timestamp (ISO 8601).")
    error_message: Optional[str] = Field(
        default=None,
        description="Error detail when FAILED, or a partial-failure summary.",
    )


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
        await asyncio.to_thread(
            extraction_engine.extract_document,
            doc_id=doc_id,
            chamber=chamber,
            file_path=file_path,
            model=model,
            user_metadata=user_metadata,
        )
        await _update_job_status(job_id, "COMPLETED")
        logger.info("Job %s [single] completed: doc_id=%s", job_id, doc_id)
    except Exception as exc:
        await _update_job_status(job_id, "FAILED", str(exc))
        logger.error("Job %s [single] failed: doc_id=%s error=%s", job_id, doc_id, exc)


async def _execute_bulk_job(
    job_id: uuid.UUID,
    chamber: Optional[str],
    model: Optional[str],
    user_metadata: Dict[str, Any],
    force: bool,
):
    """Background worker that extracts every discovered document.

    Documents are processed sequentially; progress is written to PostgreSQL after
    each one so the status endpoint can report ``processed_documents`` /
    ``total_documents``.
    """
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        documents = await asyncio.to_thread(extraction_engine.iter_documents, chamber)
        await _set_job_totals(job_id, len(documents))
        total = len(documents)
        logger.info(
            "Job %s [bulk] started: chamber=%s model=%s documents=%d force=%s",
            job_id, chamber or "all", model or extraction_engine.DEFAULT_MODEL, total, force,
        )

        processed = 0
        succeeded = 0
        skipped = 0
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
                await _update_job_progress(job_id, processed)
                continue
            try:
                await asyncio.to_thread(
                    extraction_engine.extract_document,
                    doc_id=doc["doc_id"],
                    chamber=doc["chamber"],
                    file_path=doc["file_path"],
                    model=model,
                    user_metadata=user_metadata,
                )
                succeeded += 1
                logger.info(
                    "[%d/%d] OK doc_id=%s chamber=%s",
                    index, total, doc["doc_id"], doc["chamber"],
                )
            except Exception as exc:  # keep going; record the failure
                failures.append(f"{doc['doc_id']}: {exc}")
                logger.error(
                    "[%d/%d] FAIL doc_id=%s error=%s",
                    index, total, doc["doc_id"], exc,
                )
            processed += 1
            await _update_job_progress(job_id, processed)

        logger.info(
            "Job %s [bulk] finished: parsed=%d skipped=%d failed=%d",
            job_id, succeeded, skipped, len(failures),
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
                "value": {"chamber": "senate", "force": True},
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
        if extraction_engine.is_already_parsed(doc_id) and not request.force:
            logger.info(
                "Job %s [single] SKIP doc_id=%s (already parsed) file=%s",
                job_id, doc_id, request.file_path,
            )
            async with pool.acquire() as conn:
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
                    "single",
                    1,
                    1,
                    "COMPLETED",
                    "Skipped: already parsed (set force=true to reparse)",
                )
            return {
                "job_id": str(job_id),
                "status": "COMPLETED",
                "mode": "single",
                "skipped": True,
            }

        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO parse_jobs "
                "(job_id, doc_id, chamber, model, requested_by, mode, total_documents, status) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                job_id,
                doc_id,
                chamber,
                model,
                requested_by,
                "single",
                1,
                "PENDING",
            )

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

    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO parse_jobs "
            "(job_id, chamber, model, requested_by, mode, status) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            job_id,
            chamber,
            model,
            requested_by,
            "bulk",
            "PENDING",
        )

    background_tasks.add_task(
        _execute_bulk_job,
        job_id,
        chamber,
        request.model,
        user_metadata,
        request.force or False,
    )
    return {"job_id": str(job_id), "status": "PENDING", "mode": "bulk", "skipped": False}


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
            "total_documents, processed_documents, status, "
            "created_at, updated_at, error_message "
            "FROM parse_jobs WHERE job_id = $1",
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
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "error_message": job["error_message"],
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
