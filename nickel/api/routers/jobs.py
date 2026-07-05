"""API-роутер: задачи пайплайна."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import audit_action, check_permission, get_current_user
from api.models import JobLogEntry, JobResponse
from api.runtime import job_store
from services.job_cancel import cancel as cancel_running
from services.user_messages import Msg

router = APIRouter()


@router.get("/api/v1/jobs", response_model=List[JobResponse])
async def list_jobs(
    limit: int = 50,
    active: bool = False,
    batch_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    created_by = None if user.get("role") == "admin" else user.get("email")
    jobs = job_store.list_jobs(limit=limit, active_only=active, batch_id=batch_id, created_by=created_by)
    return [JobResponse(**j) for j in jobs]


@router.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    if user.get("role") != "admin" and job.get("created_by") not in (None, user.get("email")):
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    return JobResponse(**job)


@router.get("/api/v1/jobs/{job_id}/logs", response_model=List[JobLogEntry])
async def get_job_logs(
    job_id: str,
    since_id: int = 0,
    limit: int = Query(500, ge=1, le=2000),
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    if user.get("role") != "admin" and job.get("created_by") not in (None, user.get("email")):
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    return job_store.get_logs(job_id, since_id=since_id, limit=limit)


@router.get("/api/v1/jobs/{job_id}/children", response_model=List[JobResponse])
async def get_job_children(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    if not job_store.get_job(job_id):
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    return [JobResponse(**j) for j in job_store.list_jobs(limit=200, batch_id=job_id)]


@router.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "upload")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    if user.get("role") != "admin" and job.get("created_by") not in (None, user.get("email")):
        raise HTTPException(404, Msg.JOB_NOT_FOUND)
    if job["status"] not in ("pending", "running"):
        raise HTTPException(409, Msg.JOB_ALREADY_DONE)

    def _cancel_one(jid: str) -> None:
        cancel_running(jid)
        job_store.cancel_job(jid, Msg.JOB_CANCELLED)

    _cancel_one(job_id)
    if job.get("job_type") == "batch":
        for child in job_store.list_jobs(limit=500, batch_id=job_id):
            if child["status"] in ("pending", "running"):
                _cancel_one(child["id"])

    audit_action(user, "job.cancel", job_id, {"filename": job.get("filename")})
    return JobResponse(**job_store.get_job(job_id))
