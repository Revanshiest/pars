"""Онтологический gap analysis: Material × Process × Geography/Climate из данных графа."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from services.glossary import expand_query_with_glossary
from services.neo4j_loader import Neo4jLoader
from services.platform_config import domain_processes, gap_analysis_settings
from services.store import get_store


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
    return any(term.lower() in t for term in terms if term)


_EXPAND_CACHE: Dict[tuple, List[str]] = {}


def _expand_terms(terms: List[str]) -> List[str]:
    key = tuple(sorted(terms))
    cached = _EXPAND_CACHE.get(key)
    if cached is not None:
        return cached
    expanded: Set[str] = set(terms)
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


def _gap_recommendation(scenario: Dict, missing: List[str], full: List, partial: List) -> str:
    label = scenario["label"]
    if missing:
        return (
            f"Критический пробел: нет данных по {', '.join(missing)} "
            f"для «{label}». Загрузите исследования по этим аспектам."
        )
    if not full and not partial:
        return f"Комбинация «{label}» не освещена в графе."
    if not full:
        return (
            f"Частичное покрытие «{label}»: есть факты по отдельным "
            f"измерениям, но нет связующих triple."
        )
    return f"Комбинация «{label}» покрыта ({len(full)} связующих фактов)."


def _fact_matches_dimension(
    fact: Dict[str, Any],
    terms: List[str],
    *,
    blob: Optional[str] = None,
) -> bool:
    text = blob if blob is not None else _text_blob(fact)
    expanded = _expand_terms(terms)
    return any(term.lower() in text for term in expanded if term)


def analyze_scenario(
    facts: List[Dict[str, Any]],
    scenario: Dict[str, Any],
    *,
    include_graph_paths: bool = False,
    fact_blobs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if fact_blobs is None:
        fact_blobs = [_text_blob(f) for f in facts]

    dimensions = scenario["dimensions"]
    dim_coverage: Dict[str, List[Dict]] = {}
    for dim_name, terms in dimensions.items():
        dim_coverage[dim_name] = [
            facts[i] for i, blob in enumerate(fact_blobs)
            if _fact_matches_dimension(facts[i], terms, blob=blob)
        ]

    dim_counts = {k: len(v) for k, v in dim_coverage.items()}
    all_dims = list(dimensions.keys())

    full_overlap = [
        facts[i] for i, blob in enumerate(fact_blobs)
        if all(_fact_matches_dimension(facts[i], dimensions[d], blob=blob) for d in all_dims)
    ]
    partial = [
        facts[i] for i, blob in enumerate(fact_blobs)
        if sum(1 for d in all_dims if _fact_matches_dimension(facts[i], dimensions[d], blob=blob))
        >= max(2, len(all_dims) - 1)
    ]

    missing = [d for d in all_dims if dim_counts[d] == 0]
    gap_severity = "none"
    if missing:
        gap_severity = "critical"
    elif not full_overlap:
        gap_severity = "high" if not partial else "medium"

    graph_paths = 0
    if include_graph_paths:
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
        "preset": scenario.get("preset"),
    }


def _collect_entities(facts: List[Dict[str, Any]]) -> Dict[str, Counter]:
    counters: Dict[str, Counter] = {
        "Material": Counter(),
        "Process": Counter(),
        "Geography": Counter(),
    }
    climate_terms = gap_analysis_settings().get("climate_terms") or []

    for f in facts:
        for side in ("subject", "object"):
            etype = f.get(f"{side}_type")
            name = f.get(side, "")
            if etype in counters and name:
                counters[etype][name] += 1
        geo = f.get("geography")
        if geo:
            counters["Geography"][geo] += 1
        blob = _text_blob(f)
        for term in climate_terms:
            if term.lower() in blob:
                counters["Geography"][term] += 1

    return counters


def _scenario_id(material: str, process: str, geo: Optional[str]) -> str:
    slug = re.sub(r"[^\w]+", "_", f"{material}_{process}_{geo or 'any'}".lower()).strip("_")
    return slug[:80] or "combo"


def discover_gap_scenarios(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Строит сценарии из частых Material × Process × Geography в графе."""
    settings = gap_analysis_settings()
    max_scenarios = int(settings.get("max_auto_scenarios", 20))
    max_axis = int(settings.get("max_entities_per_axis", 8))
    climate_terms = list(settings.get("climate_terms") or [])

    counters = _collect_entities(facts)
    materials = [m for m, _ in counters["Material"].most_common(max_axis)]
    processes = [p for p, _ in counters["Process"].most_common(max_axis)]
    geographies = [g for g, _ in counters["Geography"].most_common(max_axis)]

    if not materials:
        store = get_store()
        materials = [
            t["canonical"] for t in store.list_glossary(limit=50)
            if (t.get("domain") or "").lower() == "material"
        ][:max_axis]
    if not processes:
        processes = []
        for procs in domain_processes().values():
            processes.extend(procs[:2])
        processes = list(dict.fromkeys(processes))[:max_axis]

    scenarios: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def add_scenario(mat: str, proc: str, geo: Optional[str], label: Optional[str] = None):
        sid = _scenario_id(mat, proc, geo)
        if sid in seen:
            return
        seen.add(sid)
        dims: Dict[str, List[str]] = {
            "Material": _expand_terms([mat]),
            "Process": _expand_terms([proc]),
        }
        if geo:
            dims["Geography"] = _expand_terms([geo]) if geo not in ("RU", "EN", "global") else [geo]
        scenarios.append({
            "id": sid,
            "label": label or " + ".join(x for x in (mat, proc, geo) if x),
            "dimensions": dims,
            "source": "discovered",
        })

    for mat in materials:
        for proc in processes:
            if geographies:
                for geo in geographies[:4]:
                    add_scenario(mat, proc, geo)
            else:
                add_scenario(mat, proc, None)

    for domain_key, procs in domain_processes().items():
        for proc in (procs or [])[:3]:
            for mat in materials[:3]:
                geo_label = "холодный климат" if any(t in proc.lower() for t in ("выщел", "leach")) else None
                if geo_label:
                    add_scenario(
                        mat, proc, geo_label,
                        label=f"{domain_key}: {mat} + {proc} + {geo_label}",
                    )

    if climate_terms and materials and processes:
        climate = climate_terms[0]
        for mat in materials[:2]:
            for proc in processes[:2]:
                add_scenario(mat, proc, climate, label=f"{climate} + {proc} + {mat}")

    return scenarios[:max_scenarios]


def parse_gap_query(query: str) -> Dict[str, Optional[str]]:
    """Разбор запроса через глоссарий (Material / Process / Geography)."""
    material = process = climate = None
    q_lower = query.lower()

    try:
        expanded = expand_query_with_glossary(query, use_bge=False)
        matched = expanded.get("matched_terms") or []
    except Exception:
        matched = []

    store = get_store()
    for hit in matched:
        canonical = hit.get("canonical") if isinstance(hit, dict) else None
        if not canonical:
            continue
        term = next(
            (t for t in store.list_glossary(q=canonical, limit=5) if t["canonical"] == canonical),
            None,
        )
        if not term:
            continue
        domain = (term.get("domain") or "").lower()
        if domain == "material" and not material:
            material = term["canonical"]
        elif domain == "process" and not process:
            process = term["canonical"]
        elif domain in ("geography", "concept", "parameter") and not climate:
            climate = term["canonical"]

    settings = gap_analysis_settings()
    for term in settings.get("climate_terms") or []:
        if term.lower() in q_lower and not climate:
            climate = term
            break

    if not material:
        for t in store.list_glossary(q=query, limit=20):
            if (t.get("domain") or "").lower() == "material":
                forms = [t["canonical"]] + t.get("synonyms_ru", []) + t.get("synonyms_en", [])
                if any(f.lower() in q_lower for f in forms):
                    material = t["canonical"]
                    break

    if not process:
        for t in store.list_glossary(q=query, limit=20):
            if (t.get("domain") or "").lower() == "process":
                forms = [t["canonical"]] + t.get("synonyms_ru", []) + t.get("synonyms_en", [])
                if any(f.lower() in q_lower for f in forms):
                    process = t["canonical"]
                    break

    return {"material": material, "process": process, "climate": climate}


def _build_custom_scenario(
    query: Optional[str],
    material: Optional[str],
    process: Optional[str],
    climate: Optional[str],
) -> Dict[str, Any]:
    dims = {}
    if material:
        dims["Material"] = _expand_terms([material])
    if process:
        dims["Process"] = _expand_terms([process])
    if climate:
        dims["Geography"] = _expand_terms([climate])
    label = query or " + ".join(x for x in (climate, process, material) if x)
    return {
        "id": "custom_query",
        "label": label,
        "dimensions": dims,
        "source": "query",
        "preset": {
            "query": query,
            "material": material,
            "process": process,
            "climate": climate,
            "label": label,
        },
    }


def _scenario_matches_query(scenario: Dict[str, Any], query: str) -> bool:
    q = query.lower()
    if q in scenario.get("label", "").lower():
        return True
    for terms in scenario.get("dimensions", {}).values():
        if any(q in t.lower() or t.lower() in q for t in terms):
            return True
    return False


def build_suggested_presets(analyzed: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    """Пресеты для UI из критических пробелов."""
    gaps = [a for a in analyzed if a.get("is_gap")]
    gaps.sort(key=lambda x: (
        0 if x.get("gap_severity") == "critical" else 1,
        -x.get("partial_overlap_facts", 0),
    ))
    presets = []
    for g in gaps[:limit]:
        preset = g.get("preset")
        if preset:
            presets.append(preset)
            continue
        dims = g.get("dimensions") or {}
        mat = (dims.get("Material") or [None])[0]
        proc = (dims.get("Process") or [None])[0]
        geo = (dims.get("Geography") or [None])[0]
        entry: Dict[str, Any] = {"label": g.get("label", "Пробел")}
        if mat:
            entry["material"] = mat
        if proc:
            entry["process"] = proc
        if geo:
            entry["climate"] = geo
        presets.append(entry)
    return presets


def _sort_analyzed(analyzed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    analyzed.sort(key=lambda x: (
        0 if x.get("is_gap") else 1,
        0 if x.get("gap_severity") == "critical" else 1,
        -len(x.get("missing_dimensions") or []),
    ))
    return analyzed


def _build_gap_scenarios(
    facts: List[Dict[str, Any]],
    *,
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    domain: Optional[str] = None,
    auto: bool = False,
) -> Tuple[List[Dict[str, Any]], bool, Optional[str], Optional[str], Optional[str], Optional[str]]:
    if query and not (material or process or climate):
        parsed = parse_gap_query(query)
        material = material or parsed.get("material")
        process = process or parsed.get("process")
        climate = climate or parsed.get("climate")

    scenarios: List[Dict[str, Any]] = []
    auto_discovered = auto or not query

    if material or process or climate:
        scenarios.append(_build_custom_scenario(query, material, process, climate))

    if auto or (not scenarios and not query):
        scenarios.extend(discover_gap_scenarios(facts))

    if domain:
        procs = domain_processes().get(domain, [])
        for proc in procs[:5]:
            scenarios.append({
                "id": f"domain_{domain}_{proc}",
                "label": f"{domain}: {proc}",
                "dimensions": {"Process": _expand_terms([proc])},
                "source": "domain",
            })

    if query and not (material or process or climate):
        filtered = [s for s in scenarios if _scenario_matches_query(s, query)]
        if filtered:
            scenarios = filtered

    return scenarios, auto_discovered, query, domain, material, process


def iter_ontology_gaps(
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    domain: Optional[str] = None,
    auto: bool = False,
) -> Iterator[Dict[str, Any]]:
    """Постепенный анализ пробелов — по одному сценарию за yield."""
    store = get_store()
    facts = store.list_facts(limit=2000, light=True)
    fact_blobs = [_text_blob(f) for f in facts]
    scenarios, auto_discovered, query, domain, material, process = _build_gap_scenarios(
        facts,
        query=query,
        material=material,
        process=process,
        climate=climate,
        domain=domain,
        auto=auto,
    )
    total = len(scenarios)
    yield {
        "type": "start",
        "total": total,
        "query": query,
        "domain": domain,
        "auto_discovered": auto_discovered,
    }

    analyzed: List[Dict[str, Any]] = []
    for idx, scenario in enumerate(scenarios):
        result = analyze_scenario(facts, scenario, fact_blobs=fact_blobs)
        analyzed.append(result)
        yield {
            "type": "item",
            "index": idx + 1,
            "total": total,
            "gap": result,
        }

    analyzed = _sort_analyzed(analyzed)
    critical = [a for a in analyzed if a.get("is_gap")]

    from services.analytics import _compute_legacy_heuristics

    yield {
        "type": "done",
        "scenarios_analyzed": len(analyzed),
        "critical_gaps": len(critical),
        "ontology_gaps": analyzed,
        "suggested_presets": build_suggested_presets(analyzed),
        "legacy_heuristics": _compute_legacy_heuristics(domain, facts[:500]),
    }


def find_ontology_gaps(
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    domain: Optional[str] = None,
    auto: bool = False,
) -> Dict[str, Any]:
    store = get_store()
    facts = store.list_facts(limit=2000, light=True)
    fact_blobs = [_text_blob(f) for f in facts]
    scenarios, auto_discovered, query, domain, _, _ = _build_gap_scenarios(
        facts,
        query=query,
        material=material,
        process=process,
        climate=climate,
        domain=domain,
        auto=auto,
    )

    analyzed = [
        analyze_scenario(facts, s, fact_blobs=fact_blobs)
        for s in scenarios
    ]
    analyzed = _sort_analyzed(analyzed)
    critical = [a for a in analyzed if a.get("is_gap")]

    from services.analytics import _compute_legacy_heuristics

    return {
        "query": query,
        "domain": domain,
        "auto_discovered": auto_discovered,
        "scenarios_analyzed": len(analyzed),
        "critical_gaps": len(critical),
        "ontology_gaps": analyzed,
        "suggested_presets": build_suggested_presets(analyzed),
        "legacy_heuristics": _compute_legacy_heuristics(domain, facts[:500]),
    }
