"""API-роутер: загрузка документов и пакетная обработка папок (ingest).

Без тегов/префикса — пути сохранены как были в main."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile

from api.auth import audit_action, check_permission, get_current_user
from api.models import IngestFolderRequest, JobResponse
from api.runtime import UPLOAD_DIR, _run_batch_job, _run_job, job_store

router = APIRouter()


@router.post("/api/v1/documents/upload", response_model=JobResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extractor: Optional[str] = Query(None, description="ollama | yandex | auto"),
    user=Depends(get_current_user),
):
    check_permission(user, "upload")
    allowed = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls", ".json"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Формат {suffix} не поддерживается. Допустимо: {allowed}")

    job_id = job_store.create_job(file.filename or "document", "", created_by=user.get("email"))
    dest = Path(UPLOAD_DIR) / f"{job_id}_{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    with job_store._connect() as conn:
        conn.execute("UPDATE jobs SET filepath=? WHERE id=?", (str(dest), job_id))

    background_tasks.add_task(_run_job, job_id, str(dest), extractor)
    audit_action(user, "document.upload", job_id, {"filename": file.filename, "extractor": extractor})
    job = job_store.get_job(job_id)
    return JobResponse(**job)


@router.post("/api/v1/documents/ingest-folder", response_model=JobResponse)
async def ingest_folder(
    body: IngestFolderRequest,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
):
    check_permission(user, "upload")
    from services.folder_ingest import resolve_folder_path

    try:
        folder = resolve_folder_path(body.folder_path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    batch_id = job_store.create_job(
        f"batch:{folder.name}",
        str(folder),
        job_type="batch",
        folder_path=str(folder),
        created_by=user.get("email"),
    )
    job_store.append_log(batch_id, f"Пакетная обработка папки: {folder}", stage="batch")
    background_tasks.add_task(
        _run_batch_job,
        batch_id,
        folder,
        body.extractor,
        body.recursive,
    )
    audit_action(
        user,
        "document.ingest_folder",
        batch_id,
        {"folder": str(folder), "extractor": body.extractor, "recursive": body.recursive},
    )
    job = job_store.get_job(batch_id)
    return JobResponse(**job)


@router.get("/api/v1/ingest/folders")
async def list_folders(user=Depends(get_current_user)):
    check_permission(user, "read")
    from services.folder_ingest import list_ingest_folders

    return {"folders": list_ingest_folders()}
