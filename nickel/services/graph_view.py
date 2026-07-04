"""Данные для HTML-визуализации графа из SQLite (без Neo4j)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.neo4j_loader import Neo4jLoader
from services.store import get_store


def entity_node_id(name: str, entity_type: str) -> str:
    return Neo4jLoader._entity_id(name, entity_type or "Concept")


def build_graph_view(
    facts: List[Dict[str, Any]],
    *,
    entity_name: Optional[str] = None,
    limit: int = 300,
) -> Dict[str, Any]:
    """nodes + edges для GraphPage (SVG) или PyVis."""
    pool = list(facts)

    if entity_name:
        needle = entity_name.strip().lower()
        seed = [
            f for f in pool
            if needle in (f.get("subject") or "").lower()
            or needle in (f.get("object") or "").lower()
        ]
        if seed:
            names = {f["subject"] for f in seed} | {f["object"] for f in seed}
            pool = [f for f in pool if f["subject"] in names or f["object"] in names]

    pool = pool[: max(limit, 1)]

    nodes: Dict[str, Dict[str, str]] = {}
    edges: List[Dict[str, Any]] = []

    for f in pool:
        subj, obj = f.get("subject"), f.get("object")
        if not subj or not obj:
            continue
        st, ot = f.get("subject_type") or "Concept", f.get("object_type") or "Concept"
        sid, oid = entity_node_id(subj, st), entity_node_id(obj, ot)
        nodes[sid] = {"id": sid, "name": subj, "type": st}
        nodes[oid] = {"id": oid, "name": obj, "type": ot}
        edges.append({
            "source": sid,
            "target": oid,
            "label": f.get("relation") or "related_to",
            "fact_id": f.get("id"),
            "source_document": f.get("source_document"),
        })

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "facts_used": len(pool),
            "entity_filter": entity_name,
        },
    }


def load_graph_view(
    *,
    entity_name: Optional[str] = None,
    source_document: Optional[str] = None,
    limit: int = 300,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    store = get_store()
    fetch_limit = min(max(limit * 20, limit), 15000) if entity_name else min(max(limit * 3, limit), 15000)
    facts = store.list_facts(
        source_document=source_document,
        role=role,
        limit=fetch_limit,
    )
    view = build_graph_view(facts, entity_name=entity_name, limit=limit)
    view["source_document"] = source_document
    view["documents"] = _document_counts(store)
    return view


def _document_counts(store) -> List[Dict[str, Any]]:
    with store._connect() as conn:
        rows = conn.execute(
            """
            SELECT source_document, COUNT(*) AS facts
            FROM verified_facts
            WHERE source_document IS NOT NULL AND source_document != ''
            GROUP BY source_document
            ORDER BY facts DESC
            LIMIT 50
            """
        ).fetchall()
    return [{"source_document": r["source_document"], "facts": r["facts"]} for r in rows]


def facts_as_triples(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    triples = []
    for f in facts:
        triples.append({
            "subject": f["subject"],
            "subject_type": f.get("subject_type") or "Concept",
            "relation": f.get("relation") or "related_to",
            "object": f["object"],
            "object_type": f.get("object_type") or "Concept",
            "properties": f.get("properties") or {},
        })
    return triples
