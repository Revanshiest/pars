"""FastAPI: загрузка документов, отслеживание задач, семантический поиск."""

from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from api.auth import apply_search_acl, audit_action, check_permission, assert_fact_access, get_current_user
from api.middleware.security import AuditMiddleware, SecurityHeadersMiddleware
from api.jobs import JobStore
from api.models import (
    AgentQueryRequest,
    AgentQueryResponse,
    GraphQueryRequest,
    GraphViewResponse,
    HealthResponse,
    IngestFolderRequest,
    JobLogEntry,
    JobResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from api.routers.platform import router as platform_router
from agent.search_agent import KnowledgeAgent
from ontology.schema import NODE_TYPES, RELATIONS
from services.neo4j_loader import Neo4jLoader
from services.qdrant_index import QdrantIndexer
from services.pipeline_runner import (
    run_embeddings_only_pipeline,
    run_full_pipeline,
    run_import_json_pipeline,
    run_import_pair_pipeline,
)
from services.auth_bootstrap import bootstrap_admin_from_env, env_admin_spec
from services.store import get_store

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/outputs")
ONTOLOGY_DIR = Path(__file__).resolve().parent.parent / "ontology"

job_store = JobStore()
search_agent = KnowledgeAgent()


def _run_coro_in_thread(coro):
    """Отдельный event loop в worker-потоке (BGE/ sklearn не блокируют API)."""
    return asyncio.run(coro)


async def _execute_job(async_fn):
    async def work():
        return await async_fn()

    return await asyncio.to_thread(_run_coro_in_thread, work())


async def _execute_job_void(async_fn):
    async def work():
        await async_fn()

    await asyncio.to_thread(_run_coro_in_thread, work())


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    store = get_store()
    store.seed_glossary_from_file(ONTOLOGY_DIR / "glossary_seed.json")

    try:
        bootstrap_admin_from_env()
    except ValueError as exc:
        print(f"Auth: invalid AUTH_ADMIN — {exc}")

    auth_status = store.auth_status()
    spec = env_admin_spec()
    if spec:
        print(f"Auth: admin from .env ({spec['email']}); other users via /admin/")
    elif auth_status["setup_required"]:
        print("Auth: set AUTH_ADMIN=email|name|api_key in .env (or POST /api/v1/auth/setup for dev)")
    else:
        print(f"Auth: {auth_status['users_count']} users in SQLite (manage via /admin/)")

    try:
        with Neo4jLoader() as loader:
            loader.init_schema()
    except Exception:
        pass

    stale = job_store.list_jobs(limit=500, active_only=True)
    if stale:
        reason = "Прервано: перезапуск API"
        for job in stale:
            job_store.fail_job(job["id"], reason)
        print(f"Jobs: {len(stale)} незавершённых задач помечены failed после рестарта")

    yield


app = FastAPI(
    title="Nickel R&D Knowledge Graph API",
    description="KG pipeline, glossary, verification, RBAC, analytics, export",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(AuditMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(platform_router)

ADMIN_STATIC = Path(__file__).resolve().parent / "static" / "admin"
if ADMIN_STATIC.is_dir():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_STATIC), html=True), name="admin")


async def _run_job(job_id: str, filepath: str, extractor_backend: str | None = None):
    def on_progress(stage, current, total, message=None):
        job_store.update_progress(job_id, stage, current, total, message)

    async def pipeline():
        job_store.update_progress(job_id, "starting", 0, 1, "Запуск пайплайна")
        return await run_full_pipeline(
            filepath,
            job_id,
            llm_extractor=None,
            on_progress=on_progress,
            output_dir=OUTPUT_DIR,
            extractor_backend=extractor_backend or os.getenv("EXTRACTOR_BACKEND"),
        )

    try:
        result = await _execute_job(pipeline)
        job_store.complete_job(job_id, result)
    except Exception as e:
        job_store.fail_job(job_id, str(e))


async def _run_import_json_job(job_id: str, json_path: str):
    def on_progress(stage, current, total, message=None):
        job_store.update_progress(job_id, stage, current, total, message)

    async def pipeline():
        job_store.update_progress(job_id, "starting", 0, 1, "Импорт JSON")
        return await run_import_json_pipeline(
            json_path,
            job_id,
            on_progress=on_progress,
            output_dir=OUTPUT_DIR,
        )

    try:
        result = await _execute_job(pipeline)
        job_store.complete_job(job_id, result)
    except Exception as e:
        job_store.fail_job(job_id, str(e))


async def _run_index_embeddings_job(
    job_id: str,
    filepath: str,
    source_document: str | None = None,
):
    def on_progress(stage, current, total, message=None):
        job_store.update_progress(job_id, stage, current, total, message)

    async def pipeline():
        job_store.update_progress(job_id, "starting", 0, 1, "Индексация эмбеддингов")
        return await run_embeddings_only_pipeline(
            filepath,
            job_id,
            on_progress=on_progress,
            source_document=source_document,
        )

    try:
        result = await _execute_job(pipeline)
        job_store.complete_job(job_id, result)
    except Exception as e:
        job_store.fail_job(job_id, str(e))


async def _run_import_pair_job(job_id: str, json_path: str, doc_path: str):
    def on_progress(stage, current, total, message=None):
        job_store.update_progress(job_id, stage, current, total, message)

    async def pipeline():
        job_store.update_progress(job_id, "starting", 0, 2, "Импорт пары doc+json")
        return await run_import_pair_pipeline(
            json_path,
            doc_path,
            job_id,
            on_progress=on_progress,
            output_dir=OUTPUT_DIR,
        )

    try:
        result = await _execute_job(pipeline)
        job_store.complete_job(job_id, result)
    except Exception as e:
        job_store.fail_job(job_id, str(e))


async def _run_batch_pairs_job(batch_id: str, folder: Path, recursive: bool):
    async def batch_work():
        from services.pair_ingest import scan_doc_json_pairs

        pairs = scan_doc_json_pairs(folder, recursive=recursive)
        total = len(pairs)
        job_store.update_progress(batch_id, "scan", 0, max(total, 1), f"Найдено пар: {total}")
        job_store.update_batch_stats(batch_id, 0, 0, total)

        if total == 0:
            job_store.complete_job(
                batch_id,
                {"files_processed": 0, "folder": str(folder), "pairs_found": 0},
            )
            job_store.append_log(
                batch_id,
                "Пары не найдены: нужны report.pdf + report_extracted.json (или report.json)",
                level="warning",
            )
            return

        done, failed = 0, 0
        child_results = []
        for idx, (doc_path, json_path) in enumerate(pairs, start=1):
            label = f"{doc_path.name} + {json_path.name}"
            child_id = job_store.create_job(
                label,
                str(doc_path),
                job_type="import_pair",
                batch_id=batch_id,
                created_by=job_store.get_job(batch_id).get("created_by"),
            )
            job_store.append_log(batch_id, f"[{idx}/{total}] Старт: {label}", stage="batch")

            def on_progress(stage, current, progress_total, message=None, _cid=child_id):
                job_store.update_progress(_cid, stage, current, progress_total, message)

            try:
                job_store.update_progress(child_id, "starting", 0, 2, "Импорт пары")
                result = await run_import_pair_pipeline(
                    str(json_path),
                    str(doc_path),
                    child_id,
                    on_progress=on_progress,
                    output_dir=OUTPUT_DIR,
                )
                job_store.complete_job(child_id, result)
                done += 1
                child_results.append({"pair": label, "status": "completed", "job_id": child_id})
                job_store.append_log(batch_id, f"✓ {label}", stage="batch", level="success")
            except Exception as e:
                job_store.fail_job(child_id, str(e))
                failed += 1
                child_results.append({"pair": label, "status": "failed", "error": str(e), "job_id": child_id})
                job_store.append_log(batch_id, f"✗ {label}: {e}", stage="batch", level="error")

            job_store.update_batch_stats(batch_id, done, failed, total)
            job_store.update_progress(
                batch_id,
                "batch",
                done + failed,
                total,
                f"Обработано {done + failed}/{total} (ошибок: {failed})",
            )

        summary = {
            "folder": str(folder),
            "mode": "import_pairs",
            "pairs_total": total,
            "pairs_done": done,
            "pairs_failed": failed,
            "children": child_results,
        }
        if failed == total:
            job_store.fail_job(batch_id, f"Все {total} пар завершились с ошибкой")
        else:
            job_store.complete_job(batch_id, summary)
            if failed > 0:
                job_store.append_log(
                    batch_id,
                    f"Пакет завершён с ошибками: {failed}/{total}",
                    level="warning",
                )

    try:
        await _execute_job_void(batch_work)
    except Exception as e:
        job_store.fail_job(batch_id, str(e))


async def _run_uploaded_pairs_batch(
    batch_id: str,
    pairs: list[tuple[str, str, str, str]],
):
    """Пакет пар из multipart-загрузки."""

    async def batch_work():
        total = len(pairs)
        job_store.update_progress(batch_id, "scan", 1, 1, f"Пар к обработке: {total}")
        job_store.update_batch_stats(batch_id, 0, 0, total)
        job_store.append_log(batch_id, f"Пакетная загрузка пар: {total}", stage="batch")

        done, failed = 0, 0
        child_results = []
        for idx, (doc_name, doc_path, json_name, json_path) in enumerate(pairs, start=1):
            label = f"{doc_name} + {json_name}"
            child_id = job_store.create_job(
                label,
                doc_path,
                job_type="import_pair",
                batch_id=batch_id,
                created_by=job_store.get_job(batch_id).get("created_by"),
            )
            job_store.append_log(batch_id, f"[{idx}/{total}] Старт: {label}", stage="batch")

            def on_progress(stage, current, progress_total, message=None, _cid=child_id):
                job_store.update_progress(_cid, stage, current, progress_total, message)

            try:
                job_store.update_progress(child_id, "starting", 0, 2, "Импорт пары")
                result = await run_import_pair_pipeline(
                    json_path,
                    doc_path,
                    child_id,
                    on_progress=on_progress,
                    output_dir=OUTPUT_DIR,
                )
                job_store.complete_job(child_id, result)
                done += 1
                child_results.append({"pair": label, "status": "completed", "job_id": child_id})
                job_store.append_log(batch_id, f"✓ {label}", stage="batch", level="success")
            except Exception as e:
                job_store.fail_job(child_id, str(e))
                failed += 1
                child_results.append({"pair": label, "status": "failed", "error": str(e), "job_id": child_id})
                job_store.append_log(batch_id, f"✗ {label}: {e}", stage="batch", level="error")

            job_store.update_batch_stats(batch_id, done, failed, total)
            job_store.update_progress(
                batch_id,
                "batch",
                done + failed,
                total,
                f"Обработано {done + failed}/{total} (ошибок: {failed})",
            )

        summary = {
            "mode": "import_pairs_upload",
            "pairs_total": total,
            "pairs_done": done,
            "pairs_failed": failed,
            "children": child_results,
        }
        if failed == total:
            job_store.fail_job(batch_id, f"Все {total} пар завершились с ошибкой")
        else:
            job_store.complete_job(batch_id, summary)

    try:
        await _execute_job_void(batch_work)
    except Exception as e:
        job_store.fail_job(batch_id, str(e))


async def _run_uploaded_full_batch(
    batch_id: str,
    filepaths: list[str],
    extractor_backend: str | None,
):
    """Пакет загруженных файлов (mode=full)."""

    async def batch_work():
        from services.folder_ingest import sort_paths_by_size

        files = sort_paths_by_size([Path(p) for p in filepaths])
        total = len(files)
        job_store.update_progress(batch_id, "scan", 1, 1, f"Файлов к обработке: {total}")
        job_store.update_batch_stats(batch_id, 0, 0, total)
        job_store.append_log(batch_id, f"Пакетная загрузка: {total} файлов", stage="batch")

        if total == 0:
            job_store.complete_job(batch_id, {"files_processed": 0, "mode": "full_upload"})
            return

        done, failed = 0, 0
        child_results = []
        for idx, filepath in enumerate(files, start=1):
            child_id = job_store.create_job(
                filepath.name,
                str(filepath),
                job_type="single",
                batch_id=batch_id,
                created_by=job_store.get_job(batch_id).get("created_by"),
            )
            job_store.append_log(batch_id, f"[{idx}/{total}] Старт: {filepath.name}", stage="batch")

            def on_progress(stage, current, progress_total, message=None, _cid=child_id):
                job_store.update_progress(_cid, stage, current, progress_total, message)

            try:
                job_store.update_progress(child_id, "starting", 0, 1, "Запуск пайплайна")
                result = await run_full_pipeline(
                    str(filepath),
                    child_id,
                    llm_extractor=None,
                    on_progress=on_progress,
                    output_dir=OUTPUT_DIR,
                    extractor_backend=extractor_backend or os.getenv("EXTRACTOR_BACKEND"),
                )
                job_store.complete_job(child_id, result)
                done += 1
                child_results.append({"file": filepath.name, "status": "completed", "job_id": child_id})
                job_store.append_log(batch_id, f"✓ {filepath.name}", stage="batch", level="success")
            except Exception as e:
                job_store.fail_job(child_id, str(e))
                failed += 1
                child_results.append({"file": filepath.name, "status": "failed", "error": str(e), "job_id": child_id})
                job_store.append_log(batch_id, f"✗ {filepath.name}: {e}", stage="batch", level="error")

            job_store.update_batch_stats(batch_id, done, failed, total)
            job_store.update_progress(
                batch_id,
                "batch",
                done + failed,
                total,
                f"Обработано {done + failed}/{total} (ошибок: {failed})",
            )

        summary = {
            "mode": "full_upload",
            "files_total": total,
            "files_done": done,
            "files_failed": failed,
            "children": child_results,
        }
        if failed == total:
            job_store.fail_job(batch_id, f"Все {total} файлов завершились с ошибкой")
        elif failed > 0:
            job_store.complete_job(batch_id, summary)
            job_store.append_log(batch_id, f"Пакет завершён с ошибками: {failed}/{total}", level="warning")
        else:
            job_store.complete_job(batch_id, summary)

    try:
        await _execute_job_void(batch_work)
    except Exception as e:
        job_store.fail_job(batch_id, str(e))


async def _run_batch_job(
    batch_id: str,
    folder: Path,
    extractor_backend: str | None,
    recursive: bool,
):
    async def batch_work():
        from services.folder_ingest import scan_folder

        files = scan_folder(folder, recursive=recursive)
        total = len(files)
        job_store.update_progress(batch_id, "scan", 0, max(total, 1), f"Найдено файлов: {total}")
        job_store.update_batch_stats(batch_id, 0, 0, total)

        if total == 0:
            job_store.complete_job(batch_id, {"files_processed": 0, "folder": str(folder)})
            return

        done, failed = 0, 0
        child_results = []
        for idx, filepath in enumerate(files, start=1):
            child_id = job_store.create_job(
                filepath.name,
                str(filepath),
                job_type="single",
                batch_id=batch_id,
                created_by=job_store.get_job(batch_id).get("created_by"),
            )
            job_store.append_log(
                batch_id,
                f"[{idx}/{total}] Старт: {filepath.name}",
                stage="batch",
            )

            def on_progress(stage, current, progress_total, message=None, _cid=child_id):
                job_store.update_progress(_cid, stage, current, progress_total, message)

            try:
                job_store.update_progress(child_id, "starting", 0, 1, "Запуск пайплайна")
                result = await run_full_pipeline(
                    str(filepath),
                    child_id,
                    llm_extractor=None,
                    on_progress=on_progress,
                    output_dir=OUTPUT_DIR,
                    extractor_backend=extractor_backend or os.getenv("EXTRACTOR_BACKEND"),
                )
                job_store.complete_job(child_id, result)
                done += 1
                child_results.append({"file": filepath.name, "status": "completed", "job_id": child_id})
                job_store.append_log(batch_id, f"✓ {filepath.name}", stage="batch", level="success")
            except Exception as e:
                job_store.fail_job(child_id, str(e))
                failed += 1
                child_results.append({"file": filepath.name, "status": "failed", "error": str(e), "job_id": child_id})
                job_store.append_log(batch_id, f"✗ {filepath.name}: {e}", stage="batch", level="error")

            job_store.update_batch_stats(batch_id, done, failed, total)
            job_store.update_progress(
                batch_id,
                "batch",
                done + failed,
                total,
                f"Обработано {done + failed}/{total} (ошибок: {failed})",
            )

        summary = {
            "folder": str(folder),
            "files_total": total,
            "files_done": done,
            "files_failed": failed,
            "children": child_results,
        }
        if failed == total:
            job_store.fail_job(batch_id, f"Все {total} файлов завершились с ошибкой")
        elif failed > 0:
            job_store.complete_job(batch_id, summary)
            job_store.append_log(
                batch_id,
                f"Пакет завершён с ошибками: {failed}/{total}",
                level="warning",
            )
        else:
            job_store.complete_job(batch_id, summary)

    try:
        await _execute_job_void(batch_work)
    except Exception as e:
        job_store.fail_job(batch_id, str(e))


@app.get("/health", response_model=HealthResponse)
async def health():
    from services.health import check_health

    report = check_health()
    comps = report.to_dict()["components"]
    return HealthResponse(
        status=report.status,
        neo4j=comps.get("neo4j", {}).get("detail"),
        qdrant=comps.get("qdrant", {}).get("detail"),
        components=comps,
        timestamp=report.timestamp,
    )


@app.get("/ready", response_model=HealthResponse)
async def ready():
    from services.health import check_readiness

    report = check_readiness()
    comps = report.to_dict()["components"]
    if report.status == "unavailable":
        raise HTTPException(503, detail=report.to_dict())
    return HealthResponse(
        status=report.status,
        components=comps,
        timestamp=report.timestamp,
    )


@app.get("/live")
async def live():
    from services.health import check_liveness

    return check_liveness()


@app.get("/metrics")
async def metrics():
    """JSON-метрики для мониторинга (Prometheus-совместимый формат опционально)."""
    from services.health import check_health

    report = check_health()
    store = get_store()
    facts_count = len(store.list_facts(limit=10000))
    return {
        "status": report.status,
        "facts_total": facts_count,
        "users_total": store.auth_status().get("users_count", 0),
        "components": report.to_dict()["components"],
    }


@app.post("/api/v1/documents/upload", response_model=JobResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    extractor: Optional[str] = Query(None, description="ollama | yandex | auto"),
    user=Depends(get_current_user),
):
    check_permission(user, "upload")
    allowed = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls"}
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


@app.post("/api/v1/documents/import-json", response_model=JobResponse)
async def import_json_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """Импорт готового *_extracted.json в SQLite + Neo4j (+ Qdrant entities)."""
    check_permission(user, "upload")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".json":
        raise HTTPException(400, "Ожидается файл .json с полем triples")

    job_id = job_store.create_job(
        file.filename or "import.json",
        "",
        job_type="import_json",
        created_by=user.get("email"),
    )
    dest = Path(UPLOAD_DIR) / f"{job_id}_{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    with job_store._connect() as conn:
        conn.execute("UPDATE jobs SET filepath=? WHERE id=?", (str(dest), job_id))

    background_tasks.add_task(_run_import_json_job, job_id, str(dest))
    audit_action(user, "document.import_json", job_id, {"filename": file.filename})
    job = job_store.get_job(job_id)
    return JobResponse(**job)


@app.post("/api/v1/documents/index-embeddings", response_model=JobResponse)
async def index_embeddings_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_document: Optional[str] = Query(
        None,
        description="Имя документа для Qdrant (как source_file в JSON импорте)",
    ),
    user=Depends(get_current_user),
):
    """Только чанкинг + эмбеддинги в Qdrant, без LLM-извлечения фактов."""
    check_permission(user, "upload")
    allowed = {".pdf", ".md", ".txt", ".docx"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(400, f"Формат {suffix} не поддерживается. Допустимо: {allowed}")

    job_id = job_store.create_job(
        file.filename or "document",
        "",
        job_type="index_embeddings",
        created_by=user.get("email"),
    )
    dest = Path(UPLOAD_DIR) / f"{job_id}_{file.filename}"
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    with job_store._connect() as conn:
        conn.execute("UPDATE jobs SET filepath=? WHERE id=?", (str(dest), job_id))

    background_tasks.add_task(_run_index_embeddings_job, job_id, str(dest), source_document)
    audit_action(
        user,
        "document.index_embeddings",
        job_id,
        {"filename": file.filename, "source_document": source_document},
    )
    job = job_store.get_job(job_id)
    return JobResponse(**job)


@app.post("/api/v1/documents/import-pair", response_model=JobResponse)
async def import_pair(
    background_tasks: BackgroundTasks,
    document: UploadFile = File(..., description="PDF/DOCX/MD/TXT — для эмбеддингов"),
    json_file: UploadFile = File(..., description="JSON с triples — для БД"),
    user=Depends(get_current_user),
):
    """Пара: JSON → SQLite/Neo4j, документ → эмбеддинги Qdrant."""
    check_permission(user, "upload")
    doc_suffix = Path(document.filename or "").suffix.lower()
    if doc_suffix not in {".pdf", ".md", ".txt", ".docx"}:
        raise HTTPException(400, f"Документ: неподдерживаемый формат {doc_suffix}")
    if Path(json_file.filename or "").suffix.lower() != ".json":
        raise HTTPException(400, "JSON: ожидается .json")

    label = f"{document.filename} + {json_file.filename}"
    job_id = job_store.create_job(
        label,
        "",
        job_type="import_pair",
        created_by=user.get("email"),
    )
    doc_dest = Path(UPLOAD_DIR) / f"{job_id}_{document.filename}"
    json_dest = Path(UPLOAD_DIR) / f"{job_id}_{json_file.filename}"
    with open(doc_dest, "wb") as f:
        shutil.copyfileobj(document.file, f)
    with open(json_dest, "wb") as f:
        shutil.copyfileobj(json_file.file, f)

    with job_store._connect() as conn:
        conn.execute("UPDATE jobs SET filepath=? WHERE id=?", (str(doc_dest), job_id))

    background_tasks.add_task(_run_import_pair_job, job_id, str(json_dest), str(doc_dest))
    audit_action(
        user,
        "document.import_pair",
        job_id,
        {"document": document.filename, "json": json_file.filename},
    )
    job = job_store.get_job(job_id)
    return JobResponse(**job)


@app.post("/api/v1/documents/import-pairs", response_model=JobResponse)
async def import_pairs_upload(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    user=Depends(get_current_user),
):
    """Пакет пар из загруженных файлов (doc + json сопоставляются по имени)."""
    check_permission(user, "upload")
    if len(files) < 2:
        raise HTTPException(400, "Загрузите минимум 2 файла (документы + JSON)")

    batch_id = job_store.create_job(
        f"batch:import-pairs ({len(files)} files)",
        "",
        job_type="batch_pairs",
        created_by=user.get("email"),
    )
    saved: list[tuple[str, str]] = []
    for uf in files:
        dest = Path(UPLOAD_DIR) / f"{batch_id}_{uf.filename}"
        with open(dest, "wb") as f:
            shutil.copyfileobj(uf.file, f)
        saved.append((uf.filename or dest.name, str(dest)))

    from services.pair_ingest import pair_uploaded_files

    pairs = pair_uploaded_files(saved)
    if not pairs:
        job_store.fail_job(
            batch_id,
            "Пары не найдены. Имена: report.pdf + report_extracted.json (или report.json)",
        )
        raise HTTPException(
            400,
            "Не удалось сопоставить пары. Пример: report.pdf и report_extracted.json",
        )

    background_tasks.add_task(_run_uploaded_pairs_batch, batch_id, pairs)
    audit_action(user, "document.import_pairs", batch_id, {"files": len(files), "pairs": len(pairs)})
    job = job_store.get_job(batch_id)
    return JobResponse(**job)


@app.post("/api/v1/documents/upload-folder", response_model=JobResponse)
async def upload_folder(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    mode: str = Form("full"),
    extractor: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    """Загрузка папки из браузера (webkitdirectory)."""
    check_permission(user, "upload")
    if not files:
        raise HTTPException(400, "Загрузите хотя бы один файл")

    mode_norm = (mode or "full").strip().lower()
    if mode_norm not in ("full", "import_pairs"):
        raise HTTPException(400, "mode должен быть full или import_pairs")

    batch_id = job_store.create_job(
        f"batch:upload ({len(files)} files)",
        "",
        job_type="batch_pairs" if mode_norm == "import_pairs" else "batch",
        created_by=user.get("email"),
    )
    batch_dir = Path(UPLOAD_DIR) / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved: list[tuple[str, str]] = []
    for uf in files:
        rel_name = (uf.filename or "file").replace("\\", "/").lstrip("/")
        if ".." in rel_name.split("/"):
            raise HTTPException(400, f"Недопустимый путь: {uf.filename}")
        dest = batch_dir / rel_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            shutil.copyfileobj(uf.file, f)
        saved.append((rel_name, str(dest)))

    with job_store._connect() as conn:
        conn.execute("UPDATE jobs SET folder_path=? WHERE id=?", (str(batch_dir), batch_id))

    if mode_norm == "import_pairs":
        from services.pair_ingest import pair_uploaded_files

        pairs = pair_uploaded_files(saved)
        if not pairs:
            job_store.fail_job(
                batch_id,
                "Пары не найдены. Имена: report.pdf + report_extracted.json (или report.json)",
            )
            raise HTTPException(
                400,
                "Не удалось сопоставить пары. Пример: report.pdf и report_extracted.json",
            )
        job_store.append_log(batch_id, f"Пакетный импорт пар: {len(pairs)}", stage="batch")
        background_tasks.add_task(_run_uploaded_pairs_batch, batch_id, pairs)
    else:
        from services.folder_ingest import ALLOWED_EXTENSIONS

        doc_paths = [
            p for _, p in saved
            if Path(p).suffix.lower() in ALLOWED_EXTENSIONS
        ]
        if not doc_paths:
            job_store.fail_job(batch_id, "Нет поддерживаемых документов")
            raise HTTPException(400, "Нет поддерживаемых документов (pdf, docx, md, txt, xlsx)")
        job_store.append_log(batch_id, f"Пакетная обработка: {len(doc_paths)} файлов", stage="batch")
        ext = extractor if extractor and extractor != "auto" else None
        background_tasks.add_task(_run_uploaded_full_batch, batch_id, doc_paths, ext)

    audit_action(
        user,
        "document.upload_folder",
        batch_id,
        {"files": len(files), "mode": mode_norm, "extractor": extractor},
    )
    job = job_store.get_job(batch_id)
    return JobResponse(**job)


@app.post("/api/v1/documents/ingest-folder", response_model=JobResponse)
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

    mode = (body.mode or "full").strip().lower()
    if mode not in ("full", "import_pairs"):
        raise HTTPException(400, "mode должен быть full или import_pairs")

    is_pairs = mode == "import_pairs"
    batch_id = job_store.create_job(
        f"batch:{folder.name}" + (" [pairs]" if is_pairs else ""),
        str(folder),
        job_type="batch_pairs" if is_pairs else "batch",
        folder_path=str(folder),
        created_by=user.get("email"),
    )
    log_msg = (
        f"Пакетный импорт пар doc+json: {folder}"
        if is_pairs
        else f"Пакетная обработка папки: {folder}"
    )
    job_store.append_log(batch_id, log_msg, stage="batch")
    if is_pairs:
        background_tasks.add_task(_run_batch_pairs_job, batch_id, folder, body.recursive)
    else:
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
        {
            "folder": str(folder),
            "mode": mode,
            "extractor": body.extractor,
            "recursive": body.recursive,
        },
    )
    job = job_store.get_job(batch_id)
    return JobResponse(**job)


@app.get("/api/v1/ingest/folders")
async def list_folders(user=Depends(get_current_user)):
    check_permission(user, "read")
    from services.folder_ingest import list_ingest_folders

    return {"folders": list_ingest_folders()}


@app.get("/api/v1/jobs", response_model=List[JobResponse])
async def list_jobs(
    limit: int = 50,
    active: bool = False,
    batch_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    check_permission(user, "read")
    jobs = job_store.list_jobs(limit=limit, active_only=active, batch_id=batch_id)
    return [JobResponse(**j) for j in jobs]


@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobResponse(**job)


@app.get("/api/v1/jobs/{job_id}/logs", response_model=List[JobLogEntry])
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


@app.get("/api/v1/jobs/{job_id}/children", response_model=List[JobResponse])
async def get_job_children(job_id: str, user=Depends(get_current_user)):
    check_permission(user, "read")
    if not job_store.get_job(job_id):
        raise HTTPException(404, "Job not found")
    return [JobResponse(**j) for j in job_store.list_jobs(limit=200, batch_id=job_id)]


@app.post("/api/v1/search/semantic", response_model=SemanticSearchResponse)
async def semantic_search(req: SemanticSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.health import is_degraded_ok

    if not is_degraded_ok("search_vector"):
        raise HTTPException(503, "Vector search unavailable (Qdrant down). Graph/glossary may still work.")
    audit_action(user, "search.semantic", details={"query": req.query})
    from services.search_filters import filtered_search
    result = filtered_search(
        req.query, limit=req.limit, entity_type=req.entity_type, job_id=req.job_id,
        role=user["role"],
    )
    result = apply_search_acl(user, result)
    return SemanticSearchResponse(
        query=req.query, chunks=result["chunks"], entities=result["entities"]
    )


@app.post("/api/v1/search/graph")
async def graph_search(req: GraphQueryRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.health import is_degraded_ok

    if not is_degraded_ok("search_graph"):
        raise HTTPException(503, "Graph search unavailable (Neo4j down)")
    audit_action(user, "search.graph", details={"entity": req.entity_name}, request=None)
    if user.get("role") == "external_partner":
        raise HTTPException(403, "Graph traversal restricted for external partners")
    with Neo4jLoader() as loader:
        neighbors = loader.search_neighbors(req.entity_name, depth=req.depth)
    return {"entity": req.entity_name, "neighbors": neighbors}


@app.post("/api/v1/search/agent", response_model=AgentQueryResponse)
async def agent_search(req: AgentQueryRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    audit_action(user, "search.agent", details={"question": req.question})
    use_llm = os.getenv("AGENT_USE_LLM", "false").lower() == "true"
    if use_llm:
        result = await search_agent.query_with_llm(req.question)
    else:
        result = search_agent.query(req.question, max_iterations=req.max_iterations)
    return AgentQueryResponse(
        **result,
        ranked_results=result.get("ranked_results"),
        pipeline=result.get("pipeline"),
    )


@app.get("/api/v1/graph/stats")
async def graph_stats(user=Depends(get_current_user)):
    check_permission(user, "read")
    audit_action(user, "read.graph.stats")
    with Neo4jLoader() as loader:
        return loader.stats()


@app.get("/api/v1/graph/view", response_model=GraphViewResponse)
async def graph_view(
    limit: int = Query(200, ge=1, le=500),
    entity_name: Optional[str] = Query(None, description="Центр подграфа по имени сущности"),
    user=Depends(get_current_user),
):
    check_permission(user, "search")
    from services.health import is_degraded_ok

    if not is_degraded_ok("search_graph"):
        raise HTTPException(503, "Graph view unavailable (Neo4j down)")
    audit_action(user, "graph.view", details={"entity_name": entity_name, "limit": limit})
    with Neo4jLoader() as loader:
        data = loader.export_graph_view(limit=limit, center_entity=entity_name)
    return GraphViewResponse(**data)


@app.get("/api/v1/ontology")
async def get_ontology():
    return {"node_types": NODE_TYPES, "relations": RELATIONS}
