#!/usr/bin/env python3
"""
Congressional Financial Disclosures Microservice API

FastAPI-based microservice to trigger, monitor, and manage the downloading
of U.S. House of Representatives and U.S. Senate financial disclosure filings.
"""

import asyncio
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

import asyncpg
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

import download_filings
from auth_utils import require_role, verify_token

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://congress:congress_secret@localhost:5432/congress_db",
)

pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the connection pool and initialize the jobs table on startup."""
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
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
        "directly into an external mounted volume."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# In-memory job tracking status (legacy endpoints)
JOBS_STATUS: Dict[str, Any] = {
    "house": {
        "status": "IDLE",
        "last_run": None,
        "year": None,
        "stats": None,
        "message": "No jobs executed yet.",
    },
    "senate": {
        "status": "IDLE",
        "last_run": None,
        "year": None,
        "stats": None,
        "message": "No jobs executed yet.",
    },
}

JOBS_LOCK = threading.Lock()


class DownloadRequest(BaseModel):
    year: Optional[str] = Field(default=None, description="Reporting year (e.g. '2026')")
    max_downloads: Optional[int] = Field(default=0, description="Max files to download (0 = all)")
    force_download: Optional[bool] = Field(default=False, description="Force overwrite existing files")


class AsyncDownloadRequest(DownloadRequest):
    chamber: str = Field(..., description="Chamber to download: 'house', 'senate', or 'all'")


def _execute_sync(chamber: str, year: Optional[str], max_downloads: Optional[int], force_download: bool):
    """Worker function executed in background task (legacy)."""
    with JOBS_LOCK:
        JOBS_STATUS[chamber]["status"] = "RUNNING"
        JOBS_STATUS[chamber]["last_run"] = datetime.now().isoformat()
        JOBS_STATUS[chamber]["year"] = year or os.getenv("YEAR", "2026")
        JOBS_STATUS[chamber]["message"] = f"Downloading {chamber.capitalize()} filings..."

    try:
        env_file = ".env.house" if chamber == "house" else ".env.senate"
        result = download_filings.run_pipeline(
            chamber=chamber,
            env_file_path=env_file,
            year=year,
            max_downloads=max_downloads,
            force_download=force_download,
        )
        with JOBS_LOCK:
            JOBS_STATUS[chamber]["status"] = "COMPLETED"
            JOBS_STATUS[chamber]["stats"] = result.get("stats")
            JOBS_STATUS[chamber]["message"] = (
                f"Finished successfully. Downloaded: {result.get('stats', {}).get('DOWNLOADED', 0)}, "
                f"Skipped: {result.get('stats', {}).get('SKIPPED', 0)}"
            )

    except Exception as e:
        with JOBS_LOCK:
            JOBS_STATUS[chamber]["status"] = "FAILED"
            JOBS_STATUS[chamber]["message"] = str(e)


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


async def _execute_async_download(
    job_id: uuid.UUID,
    chamber: str,
    year: Optional[str],
    max_downloads: Optional[int],
    force_download: bool,
):
    """Background worker that runs the blocking download pipeline in a thread."""
    await _update_job_status(job_id, "IN_PROGRESS")
    try:
        if chamber == "all":
            for ch in ["house", "senate"]:
                env_file = ".env.house" if ch == "house" else ".env.senate"
                await asyncio.to_thread(
                    download_filings.run_pipeline,
                    chamber=ch,
                    env_file_path=env_file,
                    year=year,
                    max_downloads=max_downloads,
                    force_download=force_download,
                )
        else:
            env_file = ".env.house" if chamber == "house" else ".env.senate"
            await asyncio.to_thread(
                download_filings.run_pipeline,
                chamber=chamber,
                env_file_path=env_file,
                year=year,
                max_downloads=max_downloads,
                force_download=force_download,
            )
        await _update_job_status(job_id, "COMPLETED")
    except Exception as e:
        await _update_job_status(job_id, "FAILED", str(e))


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/", tags=["General"])
def root():
    return {
        "service": "Congressional Financial Disclosures Microservice",
        "status": "running",
        "data_directory": str(download_filings.get_base_output_dir().resolve()),
        "docs_url": "/docs",
        "endpoints": {
            "health": "/health",
            "status": "/status",
            "async_trigger": "POST /api/v1/download/trigger",
            "async_status": "GET /api/v1/download/status/{job_id}",
            "sync_house": "POST /download/house",
            "sync_senate": "POST /download/senate",
            "sync_all": "POST /download/all",
        },
    }


@app.get("/health", tags=["General"])
def health():
    """Health check endpoint for Docker container probes."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "storage_path": str(download_filings.get_base_output_dir().resolve()),
        "storage_writable": os.access(download_filings.get_base_output_dir().parent, os.W_OK),
    }


@app.get("/status", tags=["Status"])
def get_status():
    """Get the current progress, status, and stats of House and Senate ingestion jobs."""
    with JOBS_LOCK:
        return {
            "timestamp": datetime.now().isoformat(),
            "output_directory": str(download_filings.get_base_output_dir().resolve()),
            "jobs": JOBS_STATUS,
        }


# ==============================================================================
# ASYNC JOB ENDPOINTS (PostgreSQL-backed)
# ==============================================================================

@app.post(
    "/api/v1/download/trigger",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Async Download"],
)
async def trigger_download(
    request: AsyncDownloadRequest,
    background_tasks: BackgroundTasks,
    payload: dict = Depends(require_role(["admin", "downloader"])),
):
    """Trigger a download job asynchronously and return a job ID immediately."""
    if request.chamber not in ("house", "senate", "all"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="chamber must be one of: house, senate, all",
        )

    job_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO jobs (job_id, status) VALUES ($1, $2)",
            job_id,
            "PENDING",
        )

    background_tasks.add_task(
        _execute_async_download,
        job_id,
        request.chamber,
        request.year,
        request.max_downloads,
        request.force_download or False,
    )

    return {"job_id": str(job_id), "status": "PENDING"}


@app.get("/api/v1/download/status/{job_id}", tags=["Async Download"])
async def get_download_status(
    job_id: str,
    payload: dict = Depends(require_role(["admin", "downloader"])),
):
    """Return the current status of an asynchronous download job."""
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


# ==============================================================================
# LEGACY SYNC ENDPOINTS
# ==============================================================================

@app.post("/download/house", tags=["Download"])
def trigger_house_download(
    background_tasks: BackgroundTasks,
    request: Optional[DownloadRequest] = None,
    sync: bool = Query(default=False, description="Run synchronously and wait for completion"),
):
    """Trigger House of Representatives disclosure downloads."""
    with JOBS_LOCK:
        if JOBS_STATUS["house"]["status"] == "RUNNING":
            return {"status": "ALREADY_RUNNING", "message": "House download job is currently running."}

    req = request or DownloadRequest()

    if sync:
        _execute_sync("house", req.year, req.max_downloads, req.force_download or False)
        return {"status": "COMPLETED", "details": JOBS_STATUS["house"]}

    background_tasks.add_task(_execute_sync, "house", req.year, req.max_downloads, req.force_download or False)
    return {
        "status": "STARTED",
        "chamber": "House of Representatives",
        "year": req.year or os.getenv("YEAR", "2026"),
        "message": "Download initiated in background. Poll /status for progress.",
    }


@app.post("/download/senate", tags=["Download"])
def trigger_senate_download(
    background_tasks: BackgroundTasks,
    request: Optional[DownloadRequest] = None,
    sync: bool = Query(default=False, description="Run synchronously and wait for completion"),
):
    """Trigger U.S. Senate disclosure downloads (automatically handles agreement gate)."""
    with JOBS_LOCK:
        if JOBS_STATUS["senate"]["status"] == "RUNNING":
            return {"status": "ALREADY_RUNNING", "message": "Senate download job is currently running."}

    req = request or DownloadRequest()

    if sync:
        _execute_sync("senate", req.year, req.max_downloads, req.force_download or False)
        return {"status": "COMPLETED", "details": JOBS_STATUS["senate"]}

    background_tasks.add_task(_execute_sync, "senate", req.year, req.max_downloads, req.force_download or False)
    return {
        "status": "STARTED",
        "chamber": "Senate",
        "year": req.year or os.getenv("YEAR", "2026"),
        "message": "Senate download initiated in background. Poll /status for progress.",
    }


@app.post("/download/all", tags=["Download"])
def trigger_all_downloads(
    background_tasks: BackgroundTasks,
    request: Optional[DownloadRequest] = None,
):
    """Trigger downloads for both House and Senate sequentially in background."""
    req = request or DownloadRequest()

    def _sync_both():
        _execute_sync("house", req.year, req.max_downloads, req.force_download or False)
        _execute_sync("senate", req.year, req.max_downloads, req.force_download or False)

    background_tasks.add_task(_sync_both)
    return {
        "status": "STARTED",
        "message": "House and Senate downloads queued in background. Check /status for updates.",
    }
