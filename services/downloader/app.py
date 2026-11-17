#!/usr/bin/env python3
"""
Congressional Financial Disclosures Microservice API

FastAPI-based microservice to trigger, monitor, and manage the downloading
of U.S. House of Representatives and U.S. Senate financial disclosure filings.
"""

import os
import threading
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, BackgroundTasks, Query
from pydantic import BaseModel, Field

import download_filings

app = FastAPI(
    title="Congressional Financial Disclosures Microservice",
    description=(
        "Microservice to download and store U.S. House of Representatives and "
        "U.S. Senate financial disclosure filings (STOCK Act Periodic Transaction Reports & Annual Reports) "
        "directly into an external mounted volume."
    ),
    version="1.0.0",
)

# In-memory job tracking status
JOBS_STATUS: Dict[str, Any] = {
    "house": {
        "status": "IDLE",
        "last_run": None,
        "year": None,
        "stats": None,
        "message": "No jobs executed yet."
    },
    "senate": {
        "status": "IDLE",
        "last_run": None,
        "year": None,
        "stats": None,
        "message": "No jobs executed yet."
    }
}

JOBS_LOCK = threading.Lock()


class DownloadRequest(BaseModel):
    year: Optional[str] = Field(default=None, description="Reporting year (e.g. '2026')")
    max_downloads: Optional[int] = Field(default=0, description="Max files to download (0 = all)")
    force_download: Optional[bool] = Field(default=False, description="Force overwrite existing files")


def _execute_sync(chamber: str, year: Optional[str], max_downloads: Optional[int], force_download: bool):
    """Worker function executed in background task."""
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
            force_download=force_download
        )
        with JOBS_LOCK:
            JOBS_STATUS[chamber]["status"] = "COMPLETED"
            JOBS_STATUS[chamber]["stats"] = result.get("stats")
            JOBS_STATUS[chamber]["message"] = f"Finished successfully. Downloaded: {result.get('stats', {}).get('DOWNLOADED', 0)}, Skipped: {result.get('stats', {}).get('SKIPPED', 0)}"

    except Exception as e:
        with JOBS_LOCK:
            JOBS_STATUS[chamber]["status"] = "FAILED"
            JOBS_STATUS[chamber]["message"] = str(e)


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
            "sync_house": "POST /download/house",
            "sync_senate": "POST /download/senate",
            "sync_all": "POST /download/all",
        }
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
            "jobs": JOBS_STATUS
        }


@app.post("/download/house", tags=["Download"])
def trigger_house_download(
    background_tasks: BackgroundTasks,
    request: Optional[DownloadRequest] = None,
    sync: bool = Query(default=False, description="Run synchronously and wait for completion")
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
        "message": "Download initiated in background. Poll /status for progress."
    }


@app.post("/download/senate", tags=["Download"])
def trigger_senate_download(
    background_tasks: BackgroundTasks,
    request: Optional[DownloadRequest] = None,
    sync: bool = Query(default=False, description="Run synchronously and wait for completion")
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
        "message": "Senate download initiated in background. Poll /status for progress."
    }


@app.post("/download/all", tags=["Download"])
def trigger_all_downloads(
    background_tasks: BackgroundTasks,
    request: Optional[DownloadRequest] = None
):
    """Trigger downloads for both House and Senate sequentially in background."""
    req = request or DownloadRequest()

    def _sync_both():
        _execute_sync("house", req.year, req.max_downloads, req.force_download or False)
        _execute_sync("senate", req.year, req.max_downloads, req.force_download or False)

    background_tasks.add_task(_sync_both)
    return {
        "status": "STARTED",
        "message": "House and Senate downloads queued in background. Check /status for updates."
    }
