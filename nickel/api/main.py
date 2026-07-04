"""FastAPI-приложение Nickel: инициализация, middleware, lifespan, роутеры.

Бизнес-логика эндпоинтов вынесена в api/routers/*, общий рантайм
(JobStore, агент, фоновый пайплайн) — в api/runtime.py.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv()

from api.middleware.security import AuditMiddleware, SecurityHeadersMiddleware
from api.routers.admin import router as admin_router
from api.routers.analytics import router as analytics_router
from api.routers.auth import router as auth_router
from api.routers.core_search import router as core_search_router
from api.routers.export import router as export_router
from api.routers.glossary import router as glossary_router
from api.routers.graph import router as graph_router
from api.routers.ingest import router as ingest_router
from api.routers.jobs import router as jobs_router
from api.routers.notifications import router as notifications_router
from api.routers.search import router as search_router
from api.routers.system import router as system_router
from api.routers.verification import router as verification_router
from api.runtime import OUTPUT_DIR, UPLOAD_DIR, job_store
from services.neo4j_loader import Neo4jLoader
from services.auth_bootstrap import bootstrap_admin_from_env, env_admin_spec
from services.store import get_store

ONTOLOGY_DIR = Path(__file__).resolve().parent.parent / "ontology"


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

app.include_router(system_router)
app.include_router(ingest_router)
app.include_router(jobs_router)
app.include_router(core_search_router)
app.include_router(glossary_router)
app.include_router(search_router)
app.include_router(verification_router)
app.include_router(analytics_router)
app.include_router(export_router)
app.include_router(graph_router)
app.include_router(notifications_router)
app.include_router(auth_router)
app.include_router(admin_router)

ADMIN_STATIC = Path(__file__).resolve().parent / "static" / "admin"
if ADMIN_STATIC.is_dir():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_STATIC), html=True), name="admin")
