"""API-роутер: загрузка документов и пакетная обработка папок."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile

from api.auth import audit_action, check_permission, get_current_user
from api.models import IngestFolderRequest, JobResponse
from api.runtime import UPLOAD_DIR, _run_batch_job, _run_job, job_store
from services.logging_config import get_logger
from services.upload_utils import ALLOWED_SUFFIXES, max_upload_bytes, sanitize_filename
from services.user_messages import Msg

router = APIRouter()
logger = get_logger(__name__)


@router.post("/api/v1/documents/upload", response_model=JobResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extractor: Optional[str] = Query(None, description="ollama | yandex | auto"),
    user=Depends(get_current_user),
):
    check_permission(user, "upload")
    safe_name = sanitize_filename(file.filename or "document")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, Msg.UPLOAD_BAD_FORMAT)

    limit = max_upload_bytes()
    job_id = job_store.create_job(safe_name, "", created_by=user.get("email"))
    dest = Path(UPLOAD_DIR) / f"{job_id}_{safe_name}"

    try:
        total = 0
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(413, Msg.UPLOAD_TOO_LARGE)
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Upload failed job_id=%s: %s", job_id, exc)
        dest.unlink(missing_ok=True)
        raise HTTPException(500, Msg.UPLOAD_FAILED) from exc

    with job_store._connect() as conn:
        conn.execute("UPDATE jobs SET filepath=? WHERE id=?", (str(dest), job_id))

    background_tasks.add_task(_run_job, job_id, str(dest), extractor)
    audit_action(user, "document.upload", job_id, {"filename": safe_name, "extractor": extractor})
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
    job_store.append_log(batch_id, f"Пакетная обработка: {folder.name}", stage="batch")
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
