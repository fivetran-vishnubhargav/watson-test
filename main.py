"""
Watson — Investigation Orchestrator
=====================================
Receives requests from the Zendesk sidebar, queues them as background jobs,
and exposes a status endpoint the sidebar can poll.

Flow:
  POST /analyze  →  202 Accepted  +  job_id   (immediate)
  [background]   →  investigation runs async
  GET  /jobs/{job_id}  →  status + result when done
"""

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from worker import run_investigation


# ── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Watson Investigation Service",
    version="1.0.0",
    description="AI-powered initial investigation for Zendesk tickets",
)

# Allow requests from the Zendesk sidebar (CORS).
# Lock this down to your Zendesk domain in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Data models ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """What the Zendesk sidebar sends when the agent clicks Analyze."""
    ticket_id: str
    group_id: str
    schema_name: str


class JobRecord(BaseModel):
    job_id: str
    ticket_id: str
    group_id: str
    schema_name: str
    status: str           # pending | running | complete | failed
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


# ── In-memory job store ────────────────────────────────────────────────────
# Fine for a single VM. When you scale to multiple VMs, swap this dict
# for Redis (pip install redis) so all instances share state.

_jobs: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Quick liveness check. GCP health checks hit this endpoint."""
    running = sum(1 for j in _jobs.values() if j["status"] == "running")
    return {
        "status": "ok",
        "active_jobs": running,
        "total_jobs_seen": len(_jobs),
    }


@app.post("/analyze", status_code=202)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Accepts an investigation request and returns immediately with a job_id.
    The actual work runs in the background so the Zendesk sidebar doesn't
    time out waiting.
    """
    job_id = str(uuid.uuid4())

    # Register the job before starting background work
    _jobs[job_id] = {
        "job_id": job_id,
        "ticket_id": request.ticket_id,
        "group_id": request.group_id,
        "schema_name": request.schema_name,
        "status": "pending",
        "created_at": _now(),
        "completed_at": None,
        "result": None,
        "error": None,
    }

    # Hand off to background — this returns immediately to the caller
    background_tasks.add_task(_process_job, job_id, request)

    return {
        "ack": "accepted",
        "job_id": job_id,
        "ticket_id": request.ticket_id,
        "message": f"Investigation started for ticket {request.ticket_id}.",
        "poll_url": f"/jobs/{job_id}",
    }


@app.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job(job_id: str):
    """
    Poll this endpoint to check investigation progress.
    Returns the full result once status == 'complete'.
    """
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@app.get("/jobs")
async def list_jobs(limit: int = 50):
    """Returns the most recent jobs (newest first). Useful for debugging."""
    all_jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return {
        "jobs": all_jobs[:limit],
        "total": len(_jobs),
    }


# ── Background processor ───────────────────────────────────────────────────

async def _process_job(job_id: str, request: AnalyzeRequest):
    """
    Runs the investigation pipeline and writes the result back to the job store.
    Any exception is caught so the server keeps running.
    """
    _jobs[job_id]["status"] = "running"
    try:
        result = await run_investigation(
            ticket_id=request.ticket_id,
            group_id=request.group_id,
            schema_name=request.schema_name,
        )
        _jobs[job_id]["status"] = "complete"
        _jobs[job_id]["result"] = result
    except Exception as exc:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(exc)
    finally:
        _jobs[job_id]["completed_at"] = _now()
