"""API-роутер: задачи пайплайна (список, статус, логи, дочерние, отмена).

Без тегов/префикса — пути сохранены как были в main."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import audit_action, check_permission, get_current_user
from api.models import JobLogEntry, JobResponse
from api.runtime import job_store

router = APIRouter()


@router.get("/api/v1/jobs", response_model=List[JobResponse])
async def list_jobs(
    limit: int = 50,
    active: bool = False,
    batch_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    jobs = job_store.list_jobs(limit=limit, active_only=active, batch_id=batch_id)
    return [JobResponse(**j) for j in jobs]


@router.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobResponse(**job)


@router.get("/api/v1/jobs/{job_id}/logs", response_model=List[JobLogEntry])
async def get_job_logs(
    job_id: str,
    since_id: int = 0,
    limit: int = Query(500, ge=1, le=2000),
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    if not job_store.get_job(job_id):
        raise HTTPException(404, "Job not found")
    return job_store.get_logs(job_id, since_id=since_id, limit=limit)


@router.get("/api/v1/jobs/{job_id}/children", response_model=List[JobResponse])
async def get_job_children(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    if not job_store.get_job(job_id):
        raise HTTPException(404, "Job not found")
    return [JobResponse(**j) for j in job_store.list_jobs(limit=200, batch_id=job_id)]


@router.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "upload")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] not in ("pending", "running"):
        raise HTTPException(409, f"Job is already {job['status']}")
    job_store.cancel_job(job_id, "Отменено пользователем")
    audit_action(user, "job.cancel", job_id, {"filename": job.get("filename")})
    return JobResponse(**job_store.get_job(job_id))
