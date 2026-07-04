"""Онтологический gap analysis: Material × Process × Geography/Climate."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.glossary import expand_query_with_glossary
from services.neo4j_loader import Neo4jLoader
from services.store import get_store


ONTOLOGY_GAP_SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "cold_climate_hl_nickel",
        "label": "Холодный климат + heap leaching + никель",
        "dimensions": {
            "Material": ["никель", "nickel", "Ni", "NiO"],
            "Process": ["выщелачивание", "HL", "heap leaching", "leaching", "кучное"],
            "Geography": ["холод", "cold", "arctic", "север", "низк", "криоген", "subarctic", "permafrost"],
        },
    },
    {
        "id": "arctic_mine_water_ni",
        "label": "Арктика + шахтные воды + Ni",
        "dimensions": {
            "Material": ["никель", "nickel", "Ni", "шахтные воды", "mine water"],
            "Process": ["обессоливание", "очистка", "desalination", "выщелачивание"],
            "Geography": ["arctic", "аркт", "холод", "RU", "север"],
        },
    },
    {
        "id": "electrowinning_cold_cu",
        "label": "Холодный климат + электроэкстракция + медь",
        "dimensions": {
            "Material": ["медь", "copper", "Cu"],
            "Process": ["электроэкстракция", "electrowinning", "электролиз"],
            "Geography": ["холод", "cold", "arctic", "север"],
        },
    },
]


def _text_blob(fact: Dict[str, Any]) -> str:
    props = fact.get("properties") or {}
    return " ".join([
        fact.get("subject", ""),
        fact.get("object", ""),
        fact.get("relation", ""),
        fact.get("geography") or "",
        json.dumps(props, ensure_ascii=False),
    ]).lower()


def _matches_terms(text: str, terms: List[str]) -> bool:
    t = text.lower()
    return any(term.lower() in t for term in terms)


_EXPAND_CACHE: Dict[tuple, List[str]] = {}


def _expand_terms(terms: List[str]) -> List[str]:
    key = tuple(sorted(terms))
    cached = _EXPAND_CACHE.get(key)
    if cached is not None:
        return cached
    expanded = set(terms)
    for term in terms:
        try:
            g = expand_query_with_glossary(term, use_bge=False)
            expanded.update(g.get("synonyms_added", []))
            expanded.add(g.get("expanded", term))
        except Exception:
            expanded.add(term)
    result = list(expanded)
    _EXPAND_CACHE[key] = result
    return result


def _fact_matches_dimension(fact: Dict[str, Any], node_type: str, terms: List[str]) -> bool:
    expanded = _expand_terms(terms)
    blob = _text_blob(fact)
    return _matches_terms(blob, expanded)


def enrich_fact_brief(f: Dict[str, Any]) -> Dict[str, Any]:
    props = f.get("properties") or {}
    return {
        "subject": f["subject"],
        "relation": f["relation"],
        "object": f["object"],
        "year": props.get("year"),
        "source": f.get("source_document"),
        "geography": f.get("geography"),
    }


def _gap_recommendation(scenario, missing, full, partial) -> str:
    if missing:
        return (
            f"Критический пробел: нет данных по {', '.join(missing)} "
            f"для «{scenario['label']}». Загрузите исследования по этим аспектам."
        )
    if not full and not partial:
        return f"Сценарий «{scenario['label']}» не освещён в графе."
    if not full:
        return (
            f"Частичное покрытие «{scenario['label']}»: есть факты по отдельным "
            f"измерениям, но нет связующих triple."
        )
    return f"Сценарий «{scenario['label']}» покрыт ({len(full)} связующих фактов)."


def analyze_scenario(facts: List[Dict[str, Any]], scenario: Dict[str, Any]) -> Dict[str, Any]:
    dimensions = scenario["dimensions"]
    dim_coverage: Dict[str, List[Dict]] = {}
    for dim_name, terms in dimensions.items():
        dim_coverage[dim_name] = [
            f for f in facts if _fact_matches_dimension(f, dim_name, terms)
        ]

    dim_counts = {k: len(v) for k, v in dim_coverage.items()}
    all_dims = list(dimensions.keys())

    full_overlap = [
        f for f in facts
        if all(_fact_matches_dimension(f, d, dimensions[d]) for d in all_dims)
    ]
    partial = [
        f for f in facts
        if sum(1 for d in all_dims if _fact_matches_dimension(f, d, dimensions[d])) >= 2
    ]

    missing = [d for d in all_dims if dim_counts[d] == 0]
    gap_severity = "none"
    if missing:
        gap_severity = "critical"
    elif not full_overlap:
        gap_severity = "high" if not partial else "medium"

    graph_paths = 0
    try:
        anchor = dim_coverage.get("Material") or dim_coverage.get("Process") or []
        if anchor:
            with Neo4jLoader() as loader:
                graph_paths = len(loader.search_neighbors(anchor[0]["subject"], depth=2))
    except Exception:
        pass

    return {
        "scenario_id": scenario["id"],
        "label": scenario["label"],
        "dimensions": dimensions,
        "coverage": dim_counts,
        "missing_dimensions": missing,
        "full_overlap_facts": len(full_overlap),
        "partial_overlap_facts": len(partial),
        "gap_severity": gap_severity,
        "is_gap": gap_severity in ("critical", "high"),
        "sample_facts": [enrich_fact_brief(f) for f in (full_overlap or partial)[:5]],
        "graph_paths_from_anchor": graph_paths,
        "recommendation": _gap_recommendation(scenario, missing, full_overlap, partial),
    }


def parse_gap_query(query: str) -> Dict[str, Optional[str]]:
    q = query.lower()
    material = process = climate = None
    if any(x in q for x in ("ni", "никел", "nickel")):
        material = "никель"
    if any(x in q for x in ("hl", "heap", "выщелач", "leaching")):
        process = "выщелачивание"
    if any(x in q for x in ("холод", "cold", "arctic", "аркт", "климат", "север")):
        climate = "холодный климат"
    return {"material": material, "process": process, "climate": climate}


def find_ontology_gaps(
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    domain: Optional[str] = None,
) -> Dict[str, Any]:
    store = get_store()
    facts = store.list_facts(limit=1000)

    if query and not (material or process or climate):
        parsed = parse_gap_query(query)
        material = material or parsed.get("material")
        process = process or parsed.get("process")
        climate = climate or parsed.get("climate")

    scenarios = list(ONTOLOGY_GAP_SCENARIOS)
    if material or process or climate:
        scenarios.insert(0, {
            "id": "custom_query",
            "label": query or f"{climate or '?'} + {process or '?'} + {material or '?'}",
            "dimensions": {
                k: v for k, v in {
                    "Material": [material] if material else None,
                    "Process": [process] if process else None,
                    "Geography": [climate] if climate else None,
                }.items() if v
            },
        })

    if query:
        q = query.lower()
        filtered = [
            s for s in scenarios
            if any(q in t.lower() for d in s["dimensions"].values() for t in d)
            or q in s["label"].lower()
        ]
        if filtered:
            scenarios = filtered

    analyzed = [analyze_scenario(facts, s) for s in scenarios]
    critical = [a for a in analyzed if a["is_gap"]]

    from services.analytics import _compute_legacy_heuristics

    return {
        "query": query,
        "domain": domain,
        "scenarios_analyzed": len(analyzed),
        "critical_gaps": len(critical),
        "ontology_gaps": analyzed,
        "legacy_heuristics": _compute_legacy_heuristics(domain, facts[:500]),
    }
