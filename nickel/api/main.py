"""FastAPI: загрузка документов, отслеживание задач, семантический поиск."""

from __future__ import annotations

import asyncio
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, UploadFile
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
    HealthResponse,
    IngestFolderRequest,
    JobLogEntry,
    JobResponse,
    SemanticSearchRequest,
    SemanticSearchResponse,
)
from api.routers.analytics import router as analytics_router
from api.routers.export import router as export_router
from api.routers.glossary import router as glossary_router
from api.routers.graph import router as graph_router
from api.routers.notifications import router as notifications_router
from api.routers.platform import router as platform_router
from api.routers.search import router as search_router
from api.routers.verification import router as verification_router
from agent.search_agent import KnowledgeAgent
from ontology.schema import NODE_TYPES, RELATIONS
from services.neo4j_loader import Neo4jLoader
from services.qdrant_index import QdrantIndexer
from services.pipeline_runner import run_full_pipeline
from services.auth_bootstrap import bootstrap_admin_from_env, env_admin_spec
from services.store import get_store

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "data/outputs")
ONTOLOGY_DIR = Path(__file__).resolve().parent.parent / "ontology"

job_store = JobStore()
search_agent = KnowledgeAgent()
_pipeline_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pipeline")


def _run_pipeline_in_thread(
    filepath: str,
    job_id: str,
    extractor_backend: str | None,
    on_progress,
) -> dict:
    """Тяжёлый пайплайн в отдельном потоке — не блокирует HTTP."""
    return asyncio.run(
        run_full_pipeline(
            filepath,
            job_id,
            llm_extractor=None,
            on_progress=on_progress,
            output_dir=OUTPUT_DIR,
            extractor_backend=extractor_backend or os.getenv("EXTRACTOR_BACKEND"),
        )
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    for root in os.getenv("INGEST_ROOTS", "data/inbox,data/uploads").split(","):
        Path(root.strip()).mkdir(parents=True, exist_ok=True)

    store = get_store()
    seeded = store.seed_glossary_from_file(ONTOLOGY_DIR / "glossary_seed.json")
    glossary_total = store.count_glossary()
    if seeded:
        print(f"Glossary: seeded {seeded} terms from glossary_seed.json ({glossary_total} total)")
    else:
        print(f"Glossary: {glossary_total} terms in store")

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

    stale = job_store.reconcile_stale_jobs()
    if stale:
        print(f"Jobs: reconciled {stale} stale task(s) after restart")

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
app.include_router(glossary_router)
app.include_router(search_router)
app.include_router(verification_router)
app.include_router(analytics_router)
app.include_router(export_router)
app.include_router(graph_router)
app.include_router(notifications_router)

ADMIN_STATIC = Path(__file__).resolve().parent / "static" / "admin"
if ADMIN_STATIC.is_dir():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_STATIC), html=True), name="admin")


async def _run_job(job_id: str, filepath: str, extractor_backend: str | None = None):
    def on_progress(stage, current, total, message=None):
        job_store.update_progress(job_id, stage, current, total, message)

    loop = asyncio.get_running_loop()
    try:
        job_store.update_progress(job_id, "starting", 0, 1, "Запуск пайплайна")
        result = await loop.run_in_executor(
            _pipeline_executor,
            _run_pipeline_in_thread,
            filepath,
            job_id,
            extractor_backend,
            on_progress,
        )
        job_store.complete_job(job_id, result)
    except Exception as e:
        job_store.fail_job(job_id, str(e))


async def _run_batch_job(
    batch_id: str,
    folder: Path,
    extractor_backend: str | None,
    recursive: bool,
):
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
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _pipeline_executor,
                _run_pipeline_in_thread,
                str(filepath),
                child_id,
                extractor_backend,
                on_progress,
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


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
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


@app.post("/api/v1/search/semantic", response_model=SemanticSearchResponse)
async def semantic_search(req: SemanticSearchRequest, user=Depends(get_current_user)):
    check_permission(user, "search")
    from services.health import is_degraded_ok

    if not is_degraded_ok("search_vector"):
        raise HTTPException(503, "Vector search unavailable (Qdrant down). Graph/glossary may still work.")
    audit_action(user, "search.semantic", details={"query": req.query})
    from services.search_filters import filtered_search
    from services.search_runtime import run_search
    result = await run_search(
        filtered_search,
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
    from services.search_runtime import run_search

    role = user.get("role")
    use_llm = os.getenv("AGENT_USE_LLM", "false").lower() == "true"
    if use_llm:
        result = await search_agent.query_with_llm(req.question, role=role)
    else:
        result = await run_search(
            search_agent.query,
            req.question,
            req.max_iterations,
            role,
        )
    result = apply_search_acl(user, result)
    return AgentQueryResponse(**result)


@app.get("/api/v1/graph/stats")
async def graph_stats(user=Depends(get_current_user)):
    check_permission(user, "read")
    audit_action(user, "read.graph.stats")
    from services.graph_view import entity_node_id
    from services.health import is_degraded_ok

    store = get_store()
    facts = store.list_facts(role=user.get("role"), limit=50000)
    entities: set[str] = set()
    for f in facts:
        entities.add(entity_node_id(f["subject"], f.get("subject_type") or "Concept"))
        entities.add(entity_node_id(f["object"], f.get("object_type") or "Concept"))
    sqlite_stats = {"entities": len(entities), "relationships": len(facts), "source": "sqlite"}

    if is_degraded_ok("search_graph"):
        try:
            with Neo4jLoader() as loader:
                neo = loader.stats()
                return {**neo, "sqlite": sqlite_stats}
        except Exception:
            pass
    return sqlite_stats


@app.get("/api/v1/ontology")
async def get_ontology():
    return {"node_types": NODE_TYPES, "relations": RELATIONS}
