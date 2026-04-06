"""
Watson — Investigation Orchestrator
=====================================
Receives requests from the Zendesk sidebar, queues them as background jobs,
and exposes a status endpoint the sidebar can poll.

Flow:
  POST /analyze  →  202 Accepted  +  job_id   (immediate)
  [background]   →  investigation runs async
  GET  /jobs/{job_id}  →  status + result when done

Storage:
  All job state lives in Redis (localhost:6379).
  Jobs expire automatically after 24 hours.
  All 4 gunicorn workers share the same Redis, so any worker
  can answer any status poll correctly.
"""

import uuid
import json
from datetime import datetime, timezone
from typing import Optional

import redis
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Redis connection ───────────────────────────────────────────────────────
# Connects to Redis running locally on the same VM.
# decode_responses=True means Redis returns strings instead of raw bytes.

_redis = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

# How long to keep job data in Redis after completion.
# After this time Redis automatically deletes the key — no manual cleanup needed.
JOB_TTL_SECONDS = 60 * 60 * 24  # 24 hours


# ── Helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_key(job_id: str) -> str:
    """Redis key format for a job."""
    return f"watson:job:{job_id}"


def _save_job(job: dict) -> None:
    """Serialise job dict to JSON and write to Redis with a 24h TTL."""
    _redis.set(_job_key(job["job_id"]), json.dumps(job), ex=JOB_TTL_SECONDS)


def _load_job(job_id: str) -> Optional[dict]:
    """Read a job from Redis. Returns None if not found or expired."""
    raw = _redis.get(_job_key(job_id))
    if raw is None:
        return None
    return json.loads(raw)


def _update_job(job_id: str, **fields) -> None:
    """
    Load a job, apply field updates, and save it back.
    e.g. _update_job(job_id, status="running")
    """
    job = _load_job(job_id)
    if job is None:
        return
    job.update(fields)
    _save_job(job)


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


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Liveness check. Also verifies Redis is reachable."""
    try:
        _redis.ping()
        redis_status = "ok"
    except Exception as e:
        redis_status = f"error: {e}"

    return {
        "status": "ok",
        "redis": redis_status,
    }


@app.post("/analyze", status_code=202)
async def analyze(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """
    Accepts an investigation request and returns immediately with a job_id.
    The actual investigation runs in the background.
    """
    job_id = str(uuid.uuid4())

    # Write job to Redis before starting background work
    job = {
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
    _save_job(job)

    # Schedule investigation — runs after this response is sent
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
    Poll this to check progress. Returns the full result when status == complete.
    Jobs expire from Redis after 24 hours.
    """
    job = _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found or expired.")
    return job


@app.get("/jobs")
async def list_jobs(limit: int = 50):
    """
    Returns recent jobs. Scans Redis for all watson:job:* keys.
    Useful for debugging — don't call this in a hot loop in production.
    """
    keys = _redis.keys("watson:job:*")
    jobs = []
    for key in keys:
        raw = _redis.get(key)
        if raw:
            jobs.append(json.loads(raw))

    jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return {
        "jobs": jobs[:limit],
        "total": len(jobs),
    }


# ── Background processor ───────────────────────────────────────────────────

async def _process_job(job_id: str, request: AnalyzeRequest):
    """
    Runs the full investigation pipeline.
    Writes status updates to Redis so any worker can serve the poll requests.
    """
    _update_job(job_id, status="running")
    try:
        result = await run_investigation(
            ticket_id=request.ticket_id,
            group_id=request.group_id,
            schema_name=request.schema_name,
        )
        _update_job(job_id, status="complete", result=result, completed_at=_now())

    except Exception as exc:
        _update_job(job_id, status="failed", error=str(exc), completed_at=_now())
