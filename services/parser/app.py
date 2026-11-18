#!/usr/bin/env python3
"""
Congressional Disclosure Document Parser & OCR Microservice API

FastAPI microservice that parses raw House PDF and Senate HTML disclosures
stored on the external ``/data`` volume into standardized JSON documents, with
asynchronous, PostgreSQL-backed job tracking and JWT-protected endpoints.
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

import parser_engine
from auth_utils import verify_token

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
    title="Congressional Disclosure Parser & OCR Microservice",
    description=(
        "Microservice to parse U.S. House PDF and U.S. Senate HTML financial "
        "disclosure filings into standardized JSON (transactions: ticker, asset, "
        "type, date, amount range) stored on an external mounted volume."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


class ParseRequest(BaseModel):
    chamber: Optional[str] = Field(
        default=None,
        description="Chamber to parse: 'house', 'senate', 'all', or omitted for all",
    )
    doc_id: Optional[str] = Field(
        default=None, description="Parse only a single filing by DocID"
    )
    force: Optional[bool] = Field(
        default=False, description="Reparse documents even if JSON already exists"
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
    chamber: Optional[str],
    doc_id: Optional[str],
    force: bool,
):
    """Background worker that runs the blocking parse pipeline in a thread."""
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        await asyncio.to_thread(
            parser_engine.run_parse,
            chamber=chamber,
            doc_id=doc_id,
            force=force,
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
    base_dir = parser_engine.get_base_output_dir()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "storage_path": str(base_dir.resolve()),
        "storage_writable": os.access(base_dir, os.W_OK),
        "parsed_json_dir": str(parser_engine.get_parsed_json_dir().resolve()),
    }


# ==============================================================================
# PARSE JOB ENDPOINTS (PostgreSQL-backed, JWT-protected)
# ==============================================================================

@app.post(
    "/api/v1/parse/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Parse"],
)
async def trigger_parse(
    request: ParseRequest,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Trigger a parsing job asynchronously and return a job ID immediately."""
    if request.chamber and request.chamber.lower() not in ("house", "senate", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: house, senate, all",
        )

    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO parse_jobs (job_id, status) VALUES ($1, $2)",
            job_id,
            "PENDING",
        )

    background_tasks.add_task(
        _execute_parse_job,
        job_id,
        request.chamber,
        request.doc_id,
        request.force or False,
    )

    return {"job_id": str(job_id), "status": "PENDING"}


@app.get("/api/v1/parse/status/{job_id}", tags=["Parse"])
async def get_parse_status(
    job_id: str,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Return the current status of an asynchronous parse job."""
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
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
        "error_message": job["error_message"],
    }


@app.get("/api/v1/parse/document/{doc_id}", tags=["Parse"])
async def get_parsed_document(
    doc_id: str,
    payload: Dict[str, Any] = Depends(verify_token),
):
    """Return the standardized parsed JSON for a single filing by DocID."""
    parsed_dir = parser_engine.get_parsed_json_dir()
    output_path = parsed_dir / f"{doc_id}.json"
    if not output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed document not found",
        )
    with open(output_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
