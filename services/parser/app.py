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
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

import asyncpg
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

import extraction_engine
from auth_utils import require_role

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://congress:congress_secret@localhost:5432/congress_db",
)

pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and initialize the parse_jobs table on startup."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parse_jobs (
                job_id UUID PRIMARY KEY,
                doc_id VARCHAR(255),
                chamber VARCHAR(20),
                model VARCHAR(100),
                requested_by VARCHAR(255),
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
    title="Congressional Disclosure Extraction Microservice",
    description=(
        "Microservice that extracts structured data from U.S. House PDF and "
        "U.S. Senate HTML financial disclosure filings using an LLM routed "
        "through a LiteLLM Proxy (OpenRouter / Hugging Face / local Ollama). "
        "Output is standardized JSON (trades vs. non-trade disclosures) written "
        "to an external mounted volume."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


class ParseRequest(BaseModel):
    doc_id: str = Field(..., description="Document ID of the filing to extract")
    chamber: str = Field(..., description="Chamber: 'House' or 'Senate'")
    file_path: str = Field(
        ...,
        description="Path to the raw document, relative to the /data volume",
    )
    model: Optional[str] = Field(
        default=None,
        description=(
            "Optional LiteLLM model provider name (e.g. 'openrouter-gemini-flash', "
            "'hf-qwen', 'local-llm'). Defaults to the service default."
        ),
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


async def _execute_parse_job(
    job_id: uuid.UUID,
    doc_id: str,
    chamber: str,
    file_path: str,
    model: Optional[str],
    user_metadata: Dict[str, Any],
):
    """Background worker that runs the blocking extraction pipeline in a thread."""
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
    except Exception as exc:
        await _update_job_status(job_id, "FAILED", str(exc))


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/health", tags=["General"])
def health():
    """Health check endpoint for Docker container probes."""
    base_dir = extraction_engine.get_base_output_dir()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "storage_path": str(base_dir.resolve()),
        "storage_writable": os.access(base_dir, os.W_OK),
        "parsed_json_dir": str(extraction_engine.get_parsed_json_dir().resolve()),
        "litellm_proxy_url": extraction_engine.LITELLM_PROXY_URL,
        "default_model": extraction_engine.DEFAULT_MODEL,
    }


# ==============================================================================
# PARSE JOB ENDPOINTS (PostgreSQL-backed, JWT-protected, RBAC-gated)
# ==============================================================================

@app.post(
    "/api/v1/parse/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Parse"],
)
async def trigger_parse(
    request: ParseRequest,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Depends(require_role(["admin"])),
):
    """Trigger an extraction job asynchronously and return a job ID immediately.

    Requires the ``admin`` role.
    """
    if request.chamber.lower() not in ("house", "senate"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: House, Senate",
        )

    job_id = uuid.uuid4()
    requested_by = payload.get("sub")
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO parse_jobs (job_id, doc_id, chamber, model, requested_by, status) "
            "VALUES ($1, $2, $3, $4, $5, $6)",
            job_id,
            request.doc_id,
            request.chamber,
            request.model or extraction_engine.DEFAULT_MODEL,
            requested_by,
            "PENDING",
        )

    # Forward caller metadata to the LiteLLM Proxy for audit logging.
    user_metadata = {
        "user": requested_by,
        "roles": payload.get("roles", []),
    }

    background_tasks.add_task(
        _execute_parse_job,
        job_id,
        request.doc_id,
        request.chamber,
        request.file_path,
        request.model,
        user_metadata,
    )

    return {"job_id": str(job_id), "status": "PENDING"}


@app.get("/api/v1/parse/status/{job_id}", tags=["Parse"])
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
            "SELECT job_id, doc_id, chamber, model, requested_by, status, "
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
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "error_message": job["error_message"],
    }


@app.get("/api/v1/parse/document/{doc_id}", tags=["Parse"])
async def get_parsed_document(
    doc_id: str,
    payload: Dict[str, Any] = Depends(require_role(["admin", "user"])),
):
    """Return the standardized parsed JSON for a single filing by DocID."""
    parsed_dir = extraction_engine.get_parsed_json_dir()
    output_path = parsed_dir / f"{doc_id}.json"
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        )
    with open(output_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
