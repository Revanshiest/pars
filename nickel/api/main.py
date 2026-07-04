"""FastAPI-приложение Nickel: инициализация, middleware, lifespan, роутеры."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from services.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

from services.security_bootstrap import cors_origins, docs_enabled, validate_secrets

validate_secrets()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.middleware.rate_limit import RateLimitMiddleware
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
    logger.info("Glossary: %s terms (%s seeded from seed file)", glossary_total, seeded)

    try:
        bootstrap_admin_from_env()
    except ValueError as exc:
        logger.error("Invalid AUTH_ADMIN: %s", exc)

    auth_status = store.auth_status()
    spec = env_admin_spec()
    if spec:
        logger.info("Auth: admin from .env (%s)", spec["email"])
    elif auth_status["setup_required"]:
        logger.warning("Auth: no users — set AUTH_ADMIN or use setup endpoint in dev")
    else:
        logger.info("Auth: %s users in store", auth_status["users_count"])

    try:
        with Neo4jLoader() as loader:
            loader.init_schema()
        logger.info("Neo4j schema initialized")
    except Exception as exc:
        logger.warning("Neo4j unavailable at startup: %s", exc)

    stale = job_store.reconcile_stale_jobs()
    if stale:
        logger.info("Reconciled %s stale job(s) after restart", stale)

    yield


_app_kwargs = {
    "title": "Nickel R&D Knowledge Graph API",
    "description": "Карта знаний R&D: импорт, поиск, верификация, аналитика",
    "version": "0.3.0",
    "lifespan": lifespan,
}
if not docs_enabled():
    _app_kwargs["docs_url"] = None
    _app_kwargs["redoc_url"] = None
    _app_kwargs["openapi_url"] = None

app = FastAPI(**_app_kwargs)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
_origins = cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else ["http://localhost:3000"],
    allow_credentials=True,
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
