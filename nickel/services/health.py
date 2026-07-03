"""Health checks, readiness и graceful degradation."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from services.store import get_store


@dataclass
class ComponentStatus:
    name: str
    status: str  # ok | degraded | unavailable
    detail: str = ""
    latency_ms: Optional[float] = None


@dataclass
class HealthReport:
    status: str  # ok | degraded | unavailable
    components: List[ComponentStatus] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "components": {
                c.name: {
                    "status": c.status,
                    "detail": c.detail,
                    "latency_ms": c.latency_ms,
                }
                for c in self.components
            },
        }


def _check_sqlite() -> ComponentStatus:
    t0 = time.perf_counter()
    try:
        store = get_store()
        auth = store.auth_status()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return ComponentStatus(
            "sqlite",
            "ok",
            f"users={auth.get('users_count', 0)}",
            ms,
        )
    except Exception as e:
        return ComponentStatus("sqlite", "unavailable", str(e))


def _check_neo4j() -> ComponentStatus:
    t0 = time.perf_counter()
    try:
        from services.neo4j_loader import Neo4jLoader

        with Neo4jLoader() as loader:
            stats = loader.stats()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return ComponentStatus(
            "neo4j",
            "ok",
            f"{stats.get('entities', 0)} entities, {stats.get('relationships', 0)} rels",
            ms,
        )
    except Exception as e:
        return ComponentStatus("neo4j", "unavailable", str(e))


def _check_qdrant() -> ComponentStatus:
    t0 = time.perf_counter()
    try:
        from services.qdrant_index import QdrantIndexer

        QdrantIndexer().ensure_collections()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return ComponentStatus("qdrant", "ok", "collections ready", ms)
    except Exception as e:
        return ComponentStatus("qdrant", "unavailable", str(e))


def _check_ollama() -> ComponentStatus:
    if os.getenv("SKIP_OLLAMA_HEALTH", "").lower() == "true":
        return ComponentStatus("ollama", "degraded", "check skipped")
    t0 = time.perf_counter()
    try:
        import urllib.request

        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        req = urllib.request.Request(f"{base}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return ComponentStatus("ollama", "ok", base, ms)
    except Exception as e:
        return ComponentStatus("ollama", "degraded", f"optional: {e}")


def _aggregate(components: List[ComponentStatus]) -> str:
    names = {c.name: c.status for c in components}
    if names.get("sqlite") == "unavailable":
        return "unavailable"
    core = [names.get("neo4j"), names.get("qdrant")]
    if any(s == "unavailable" for s in core):
        return "degraded"
    if any(s == "degraded" for s in names.values()):
        return "degraded"
    return "ok"


def check_health(include_ollama: bool = True) -> HealthReport:
    components = [_check_sqlite(), _check_neo4j(), _check_qdrant()]
    if include_ollama:
        components.append(_check_ollama())
    return HealthReport(status=_aggregate(components), components=components)


def check_liveness() -> Dict[str, str]:
    return {"status": "ok"}


def check_readiness() -> HealthReport:
    """Readiness: SQLite обязателен; Neo4j/Qdrant могут быть degraded."""
    report = check_health(include_ollama=False)
    sqlite_ok = any(c.name == "sqlite" and c.status == "ok" for c in report.components)
    if not sqlite_ok:
        report.status = "unavailable"
    return report


def is_degraded_ok(feature: str) -> bool:
    """Graceful degradation: какие фичи доступны при partial outage."""
    report = check_health(include_ollama=False)
    statuses = {c.name: c.status for c in report.components}

    if feature in ("glossary", "auth", "audit", "verification", "export_md"):
        return statuses.get("sqlite") == "ok"
    if feature in ("search_vector", "semantic"):
        return statuses.get("qdrant") == "ok" and statuses.get("sqlite") == "ok"
    if feature in ("search_graph", "graph_stats"):
        return statuses.get("neo4j") == "ok"
    if feature in ("pipeline", "upload"):
        return statuses.get("sqlite") == "ok"
    return report.status != "unavailable"
