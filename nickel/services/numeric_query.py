"""Числовой query-движок по SQLite + Neo4j."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.neo4j_loader import Neo4jLoader
from services.numeric_parser import constraint_matches_query, parse_numeric_query
from services.store import get_store


def search_by_numeric_query(
    query: str,
    limit: int = 50,
    geography: Optional[str] = None,
    verification_status: Optional[str] = None,
) -> Dict[str, Any]:
    parsed = parse_numeric_query(query)
    if not parsed:
        return {
            "query": query,
            "parsed": None,
            "error": "Не удалось распознать числовой запрос. Пример: «сульфаты < 200 мг/л»",
            "results": [],
        }

    store = get_store()
    facts = store.list_facts(status=verification_status, geography=geography, limit=500)

    matched = []
    for fact in facts:
        props = fact.get("properties") or {}
        constraints = props.get("numeric_constraints") or []
        if not constraints:
            # fallback: сканировать все properties
            constraints = _constraints_from_legacy_props(props)

        for c in constraints:
            if constraint_matches_query(c, parsed):
                matched.append({**fact, "matched_constraint": c})
                break

    neo4j_results = _search_neo4j_numeric(parsed, limit)

    return {
        "query": query,
        "parsed": parsed,
        "results": matched[:limit],
        "neo4j_results": neo4j_results[:limit],
        "total_matched": len(matched),
    }


def _constraints_from_legacy_props(props: dict) -> List[dict]:
    out = []
    for key, val in props.items():
        if key in ("numeric_constraints", "description", "source_file"):
            continue
        try:
            num = float(str(val).replace(",", ".").rstrip("°Ccf"))
            out.append({
                "parameter": key,
                "operator": "=",
                "value": num,
                "unit": "mg/l" if "conc" in key else "unknown",
                "raw_text": f"{key}={val}",
            })
        except ValueError:
            continue
    return out


def _search_neo4j_numeric(parsed: dict, limit: int) -> List[dict]:
    try:
        with Neo4jLoader() as loader:
            cypher = """
            MATCH (s:Entity)-[r:REL]->(o:Entity)
            WHERE r.properties IS NOT NULL
            RETURN s.name AS subject, s.type AS subject_type,
                   r.type AS relation, o.name AS object, o.type AS object_type,
                   r.properties AS properties, r.geography AS geography
            LIMIT 500
            """
            rows = loader.query(cypher)
    except Exception:
        return []

    results = []
    param = parsed.get("parameter", "").lower()
    for row in rows:
        props = row.get("properties") or {}
        if isinstance(props, str):
            import json
            try:
                props = json.loads(props)
            except Exception:
                props = {}
        constraints = props.get("numeric_constraints") or _constraints_from_legacy_props(props)
        text_blob = f"{row.get('subject','')} {row.get('object','')}".lower()
        if param and param not in text_blob and not any(
            constraint_matches_query(c, parsed) for c in constraints
        ):
            continue
        for c in constraints:
            if constraint_matches_query(c, parsed):
                results.append({**row, "matched_constraint": c})
                break
        if len(results) >= limit:
            break
    return results
