"""Данные для HTML-визуализации графа из SQLite (без Neo4j)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.glossary import normalize_entity
from services.neo4j_loader import Neo4jLoader
from services.store import get_store

# При слиянии дубликатов по имени — приоритет типа для цвета узла
TYPE_PRIORITY: Dict[str, int] = {
    "Material": 0,
    "Process": 1,
    "Equipment": 2,
    "Facility": 3,
    "Parameter": 4,
    "Metric": 5,
    "Property": 6,
    "Product": 7,
    "Expert": 8,
    "Document": 9,
    "Concept": 50,
}


def entity_node_id(name: str, entity_type: str) -> str:
    return Neo4jLoader._entity_id(name, entity_type or "Concept")


def canonical_node_id(canonical_name: str) -> str:
    slug = canonical_name.strip().lower().replace(" ", "_")
    return f"ent:{slug}"


def _pick_type(current: str, candidate: str) -> str:
    cur_p = TYPE_PRIORITY.get(current, 100)
    cand_p = TYPE_PRIORITY.get(candidate, 100)
    return current if cur_p <= cand_p else candidate


def _resolve_entity(
    name: str,
    entity_type: str,
    glossary_index: Dict[str, str],
    nodes: Dict[str, Dict[str, Any]],
) -> str:
    """Один канонический узел на сущность (медь Material + медь Concept → один узел)."""
    canonical = normalize_entity(name.strip(), index=glossary_index)
    nid = canonical_node_id(canonical)
    etype = entity_type or "Concept"

    if nid not in nodes:
        nodes[nid] = {
            "id": nid,
            "name": canonical,
            "type": etype,
            "aliases": [],
        }
    else:
        nodes[nid]["type"] = _pick_type(nodes[nid]["type"], etype)
        raw = name.strip()
        if raw.lower() != canonical.lower() and raw not in nodes[nid]["aliases"]:
            nodes[nid]["aliases"].append(raw)

    return nid


def build_graph_view(
    facts: List[Dict[str, Any]],
    *,
    entity_name: Optional[str] = None,
    limit: int = 300,
    glossary_index: Optional[Dict[str, str]] = None,
    neighbor_edge_limit: Optional[int] = None,
) -> Dict[str, Any]:
    """nodes + edges для GraphPage (SVG) или PyVis."""
    glossary_index = glossary_index or get_store().build_glossary_index()
    pool = list(facts)

    if entity_name and not pool:
        needle = entity_name.strip().lower()
        pool = [
            f for f in facts
            if needle in (f.get("subject") or "").lower()
            or needle in (f.get("object") or "").lower()
        ]

    if entity_name:
        needle = entity_name.strip().lower()
        canon = normalize_entity(entity_name, index=glossary_index).lower()
        seed = [
            f for f in pool
            if needle in (f.get("subject") or "").lower()
            or needle in (f.get("object") or "").lower()
            or canon in (f.get("subject") or "").lower()
            or canon in (f.get("object") or "").lower()
        ]
        if seed:
            canonical_names = set()
            for f in seed:
                for n in (f.get("subject"), f.get("object")):
                    if n:
                        canonical_names.add(normalize_entity(n, index=glossary_index).lower())
            pool = [
                f for f in pool
                if normalize_entity(f["subject"], index=glossary_index).lower() in canonical_names
                or normalize_entity(f["object"], index=glossary_index).lower() in canonical_names
            ]
    else:
        pool = pool[: max(limit, 1)]

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []

    for f in pool:
        subj, obj = f.get("subject"), f.get("object")
        if not subj or not obj:
            continue
        st, ot = f.get("subject_type") or "Concept", f.get("object_type") or "Concept"
        sid = _resolve_entity(subj, st, glossary_index, nodes)
        oid = _resolve_entity(obj, ot, glossary_index, nodes)
        if sid == oid:
            continue
        edges.append({
            "source": sid,
            "target": oid,
            "label": f.get("relation") or "related_to",
            "fact_id": f.get("id"),
            "source_document": f.get("source_document"),
        })

    node_list = []
    for n in nodes.values():
        entry = {"id": n["id"], "name": n["name"], "type": n["type"]}
        if n.get("aliases"):
            entry["aliases"] = n["aliases"]
        node_list.append(entry)

    if entity_name:
        node_list, edges = _trim_to_entity_neighborhood(
            node_list, edges, entity_name, glossary_index, edge_limit=neighbor_edge_limit
        )

    return {
        "nodes": node_list,
        "edges": edges,
        "stats": {
            "nodes": len(node_list),
            "edges": len(edges),
            "facts_used": len(pool),
            "entity_filter": entity_name,
            "merged_by_name": True,
        },
    }


def _find_center_node_ids(
    node_list: List[Dict[str, Any]],
    entity_name: str,
    glossary_index: Dict[str, str],
) -> set[str]:
    needle = entity_name.strip().lower()
    if not needle:
        return set()
    canon = normalize_entity(entity_name, index=glossary_index).lower()

    exact: List[str] = []
    alias_match: List[str] = []
    partial: List[tuple[int, str]] = []

    for n in node_list:
        name_l = (n.get("name") or "").lower()
        if name_l == needle or name_l == canon:
            exact.append(n["id"])
            continue
        matched_alias = False
        for alias in n.get("aliases") or []:
            al = alias.lower()
            if al == needle or al == canon:
                alias_match.append(n["id"])
                matched_alias = True
                break
        if matched_alias:
            continue
        if needle in name_l or name_l in needle or canon in name_l:
            partial.append((len(name_l), n["id"]))

    if exact:
        return {exact[0]}
    if alias_match:
        return {alias_match[0]}
    if partial:
        partial.sort()
        return {partial[0][1]}
    return set()


def _trim_to_entity_neighborhood(
    node_list: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    entity_name: str,
    glossary_index: Dict[str, str],
    edge_limit: Optional[int] = None,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Центральный узел и все связи (edge_limit=None — без ограничения)."""
    center_ids = _find_center_node_ids(node_list, entity_name, glossary_index)
    if not center_ids:
        return [], []

    incident = [
        e for e in edges
        if e["source"] in center_ids or e["target"] in center_ids
    ]
    if edge_limit is not None:
        incident.sort(
            key=lambda e: (
                0 if e["source"] in center_ids and e["target"] in center_ids else 1,
                -(len(e.get("label") or "")),
            )
        )
        picked = incident[: max(edge_limit, 1)]
    else:
        picked = incident

    keep_ids = set(center_ids)
    for e in picked:
        keep_ids.add(e["source"])
        keep_ids.add(e["target"])

    nodes = [n for n in node_list if n["id"] in keep_ids]
    if not nodes and center_ids:
        nodes = [n for n in node_list if n["id"] in center_ids]
    return nodes, picked


def view_to_triples(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id = {n["id"]: n for n in view.get("nodes", [])}
    triples = []
    for e in view.get("edges", []):
        s = by_id.get(e["source"])
        t = by_id.get(e["target"])
        if not s or not t:
            continue
        triples.append({
            "subject": s["name"],
            "subject_type": s.get("type") or "Concept",
            "relation": e.get("label") or "related_to",
            "object": t["name"],
            "object_type": t.get("type") or "Concept",
            "properties": {},
        })
    return triples


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
        query=entity_name,
        role=role,
        limit=fetch_limit,
    )
    if entity_name and len(facts) < 20:
        glossary_index = store.build_glossary_index()
        from services.glossary import normalize_entity
        canon = normalize_entity(entity_name, index=glossary_index)
        extra_queries = {entity_name.strip(), canon}
        for alias_q in extra_queries:
            if not alias_q:
                continue
            extra = store.list_facts(
                source_document=source_document,
                query=alias_q,
                role=role,
                limit=fetch_limit,
            )
            seen = {f.get("id") for f in facts}
            for f in extra:
                if f.get("id") not in seen:
                    facts.append(f)
        if len(facts) < 20:
            extra = store.list_facts(
                source_document=source_document,
                role=role,
                limit=fetch_limit,
            )
            seen = {f.get("id") for f in facts}
            for f in extra:
                if f.get("id") not in seen:
                    facts.append(f)
    view = build_graph_view(
        facts,
        entity_name=entity_name,
        limit=limit,
    )
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
        out = []
        for r in rows:
            doc = r["source_document"]
            ent_row = conn.execute(
                """
                SELECT COUNT(*) AS c FROM (
                    SELECT DISTINCT LOWER(subject) AS e FROM verified_facts WHERE source_document=?
                    UNION
                    SELECT DISTINCT LOWER(object) AS e FROM verified_facts WHERE source_document=?
                )
                """,
                (doc, doc),
            ).fetchone()
            out.append({
                "source_document": doc,
                "facts": r["facts"],
                "entities": int(ent_row["c"]) if ent_row else 0,
            })
    return out


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
