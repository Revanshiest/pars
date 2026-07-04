"""API-роутер: системные и справочные эндпоинты (health/ready/live/metrics,
ontology, graph stats). Без тегов и префикса — пути сохранены как были в main."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth import audit_action, check_permission, get_current_user
from api.models import HealthResponse
from ontology.schema import NODE_TYPES, RELATIONS
from services.neo4j_loader import Neo4jLoader
from services.store import get_store

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
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


@router.get("/ready", response_model=HealthResponse)
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


@router.get("/live")
async def live():
    from services.health import check_liveness

    return check_liveness()


@router.get("/metrics")
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


@router.get("/api/v1/graph/stats")
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


@router.get("/api/v1/ontology")
async def get_ontology():
    return {"node_types": NODE_TYPES, "relations": RELATIONS}
