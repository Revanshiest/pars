"""Синтез литобзора, пробелы в знаниях, рекомендации, сравнительный анализ."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from services.expert_recommender import recommend_experts
from services.gap_analysis import find_ontology_gaps
from services.neo4j_loader import Neo4jLoader
from services.platform_config import compare_defaults, domain_processes
from services.search_filters import filtered_search
from services.store import get_store
from services.synthesis_llm import synthesize_literature_review
from services.user_messages import Msg
from services.verification import aggregate_by_source_type, enrich_fact, internal_vs_publication_summary


def _year_from_fact(fact: Dict[str, Any], doc_years: Dict[str, int]) -> Optional[int]:
    props = fact.get("properties") or {}
    year = props.get("year")
    if year is not None:
        try:
            return int(year)
        except (TypeError, ValueError):
            pass
    src = fact.get("source_document")
    if src and src in doc_years:
        return doc_years[src]
    return None


def group_facts_by_year(
    facts: List[Dict[str, Any]],
    chunks: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    store = get_store()
    doc_years = {
        d["source_document"]: d["year"]
        for d in store.list_documents(limit=500)
        if d.get("year")
    }

    by_year: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in facts:
        y = _year_from_fact(f, doc_years)
        key = str(y) if y else "unknown"
        by_year[key].append({
            "triple": f"{f['subject']} —[{f['relation']}]→ {f['object']}",
            "title": f"{f['subject']} → {f['object']}",
            "source": f.get("source_document"),
            "verification_status": f.get("verification_status"),
            "confidence": f.get("confidence"),
        })

    if chunks:
        for c in chunks:
            doc = c.get("document", "")
            y = doc_years.get(doc)
            key = str(y) if y else "unknown"
            by_year[key].append({
                "type": "excerpt",
                "document": doc,
                "text": (c.get("text") or "")[:120],
            })

    summary = {
        year: {"count": len(items), "facts": sum(1 for i in items if "triple" in i)}
        for year, items in by_year.items()
    }
    sorted_years = dict(sorted(by_year.items(), key=lambda x: x[0], reverse=True))
    return {
        "by_year": sorted_years,
        "year_summary": summary,
        "years_present": [y for y in summary if y != "unknown"],
    }


def generate_literature_review(
    topic: str,
    geography: Optional[str] = None,
    min_confidence: Optional[float] = None,
    use_llm: Optional[bool] = None,
) -> Dict[str, Any]:
    data = filtered_search(
        topic, limit=20, geography=geography,
        min_confidence=min_confidence, verification_status="verified",
    )
    all_data = filtered_search(topic, limit=20, geography=geography)
    if not all_data.get("verified_facts"):
        all_data = filtered_search(topic, limit=20)

    facts = all_data.get("verified_facts", [])
    chunks = all_data.get("chunks", [])
    entities = all_data.get("entities", [])

    if not facts and not chunks:
        return {
            "topic": topic,
            "confidence": 0,
            "sources_count": 0,
            "verified_sources": 0,
            "summary": Msg.LIT_REVIEW_NO_DATA,
            "llm_synthesized": False,
            "synthesis_mode": "empty",
            "consensus_findings": [],
            "disagreements": [],
        }

    by_method: Dict[str, List] = defaultdict(list)
    by_geo: Dict[str, List] = defaultdict(list)
    consensus = []
    disagreements = []

    for f in facts:
        by_method[f.get("relation", "related")].append(f)
        by_geo[f.get("geography") or "unknown"].append(f)
        if f.get("relation") == "contradicts":
            disagreements.append(f)
        elif f.get("verification_status") == "verified":
            consensus.append(f)

    key_findings = [f for f in facts if f.get("relation") != "contradicts"]
    if not consensus:
        consensus = key_findings

    verified_count = sum(1 for f in facts if f.get("verification_status") == "verified")
    sources_count = len(chunks) + len(facts)
    confidence = (
        0.0 if sources_count == 0
        else round(min(0.95, 0.35 + 0.05 * len(chunks) + 0.08 * verified_count), 2)
    )
    enriched_facts = [enrich_fact(f) for f in facts]
    year_data = group_facts_by_year(enriched_facts, chunks)

    sections = {
        "topic": topic,
        "confidence": confidence,
        "sources_count": sources_count,
        "verified_sources": verified_count,
        "by_method": {k: len(v) for k, v in by_method.items()},
        "by_geography": {k: len(v) for k, v in by_geo.items()},
        "by_year": year_data["by_year"],
        "year_summary": year_data["year_summary"],
        "years_present": year_data["years_present"],
        "by_source_type": aggregate_by_source_type(enriched_facts),
        "internal_vs_publication": internal_vs_publication_summary(enriched_facts),
        "consensus_findings": [enrich_fact(f) for f in consensus[:10]],
        "key_findings": [enrich_fact(f) for f in key_findings[:12]],
        "disagreements": [enrich_fact(f) for f in disagreements[:10]],
        "document_excerpts": chunks[:8],
        "entities": entities[:10],
    }

    summary, llm_used = synthesize_literature_review(topic, sections, force_llm=use_llm)
    sections["summary"] = summary
    sections["llm_synthesized"] = llm_used
    sections["synthesis_mode"] = "llm" if llm_used else "structured"
    return sections


def find_knowledge_gaps(
    domain: Optional[str] = None,
    query: Optional[str] = None,
    material: Optional[str] = None,
    process: Optional[str] = None,
    climate: Optional[str] = None,
    auto: bool = False,
) -> Dict[str, Any]:
    if query or material or process or climate or auto:
        return find_ontology_gaps(
            query=query, material=material, process=process,
            climate=climate, domain=domain, auto=auto or not query,
        )
    return _legacy_gap_heuristics(domain)


def _compute_legacy_heuristics(
    domain: Optional[str] = None,
    facts: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    store = get_store()
    facts = facts if facts is not None else store.list_facts(limit=500)
    processes = set()
    materials = set()
    geographies = set()
    combos = set()

    for f in facts:
        if f["subject_type"] == "Process":
            processes.add(f["subject"])
        if f["object_type"] == "Process":
            processes.add(f["object"])
        if f["subject_type"] == "Material":
            materials.add(f["subject"])
        if f["object_type"] == "Material":
            materials.add(f["object"])
        if f.get("geography"):
            geographies.add(f["geography"])
        if f["subject_type"] in ("Material", "Process") and f["object_type"] in ("Material", "Process"):
            combos.add((f["subject"], f["object"], f.get("geography")))

    domains = domain_processes()
    target_processes = domains.get(domain, []) if domain else []
    if not target_processes:
        for procs in domains.values():
            target_processes.extend(procs)

    uncovered = [p for p in target_processes if not any(p.lower() in x.lower() for x in processes)]
    weak_combos = []
    combo_counts = Counter((f["subject"], f["object"]) for f in facts)
    for (s, o), cnt in combo_counts.items():
        if cnt == 1:
            weak_combos.append({"material_or_process_a": s, "material_or_process_b": o, "sources": cnt})

    ru_only = [f for f in facts if f.get("geography") == "RU"]
    en_only = [f for f in facts if f.get("geography") == "EN"]
    ru_topics = {f["subject"] for f in ru_only} - {f["subject"] for f in en_only}
    en_topics = {f["subject"] for f in en_only} - {f["subject"] for f in ru_only}

    return {
        "uncovered_processes": uncovered[:15],
        "weakly_supported_combinations": weak_combos[:20],
        "ru_only_topics": list(ru_topics)[:15],
        "en_only_topics": list(en_topics)[:15],
        "total_combinations": len(combos),
        "geographies_present": list(geographies),
    }


def _legacy_gap_heuristics(domain: Optional[str] = None) -> Dict[str, Any]:
    heuristics = _compute_legacy_heuristics(domain)
    ontology = find_ontology_gaps(domain=domain, auto=True)
    return {
        **heuristics,
        "ontology_gaps": ontology.get("ontology_gaps", []),
        "critical_gaps": ontology.get("critical_gaps", 0),
    }


def generate_recommendations(topic: str) -> Dict[str, Any]:
    data = filtered_search(topic, limit=10)
    store = get_store()
    facts = store.list_facts(limit=200)
    terms = topic.lower()

    similar_cases = []
    related_topics = set()
    for f in facts:
        if terms in f["subject"].lower() or terms in f["object"].lower():
            similar_cases.append({
                "subject": f["subject"],
                "relation": f["relation"],
                "object": f["object"],
                "geography": f.get("geography"),
                "confidence": f.get("confidence"),
                "year": (f.get("properties") or {}).get("year"),
            })
            related_topics.add(f["subject"])
            related_topics.add(f["object"])

    expert_data = recommend_experts(topic)
    gaps = find_knowledge_gaps(query=topic)

    return {
        "topic": topic,
        "experts": expert_data["experts"],
        "experts_count": expert_data["experts_count"],
        "has_explicit_experts": expert_data["has_explicit_experts"],
        "fallback_used": expert_data["fallback_used"],
        "similar_cases": similar_cases[:10],
        "related_topics": list(related_topics - {topic})[:15],
        "suggested_actions": _suggest_actions(topic, gaps, similar_cases, expert_data),
        "knowledge_gaps_hint": gaps.get("ontology_gaps", [])[:3],
        "related_processes": expert_data.get("related_processes", []),
        "entities": data.get("entities", [])[:5],
    }


def _suggest_actions(topic, gaps, cases, expert_data) -> List[str]:
    actions = []
    if not cases:
        actions.append(f"Загрузить документы по теме «{topic}» через API upload.")
    og = gaps.get("ontology_gaps") or []
    critical = [g for g in og if g.get("is_gap")]
    if critical:
        actions.append(f"Закрыть онтологический пробел: {critical[0]['label']}.")
    if gaps.get("uncovered_processes"):
        actions.append(f"Изучить процессы: {', '.join(gaps['uncovered_processes'][:3])}.")
    if expert_data.get("fallback_used"):
        actions.append(
            "Явные Expert-узлы не найдены — показаны авторы документов; "
            "добавьте Expert через редактор графа или загрузите каталог сотрудников."
        )
    elif expert_data.get("related_processes") and not expert_data.get("has_explicit_experts"):
        actions.append(
            f"Смежные процессы по теме: {', '.join(expert_data['related_processes'][:3])}."
        )
    elif expert_data.get("experts"):
        top = expert_data["experts"][0]["name"]
        actions.append(f"Привлечь эксперта: {top}.")
    actions.append("Верифицировать pending-факты по теме через /verification/queue.")
    return actions


def _extract_tech_metrics(facts: List[Dict], param_keys: List[str]) -> Dict[str, Any]:
    """Извлекает числовые и именованные параметры из properties и numeric_constraints."""
    metrics: Dict[str, Any] = {}
    for f in facts:
        props = f.get("properties") or {}
        for c in props.get("numeric_constraints") or []:
            if not isinstance(c, dict):
                continue
            key = c.get("parameter") or c.get("raw_text") or "value"
            entry = {
                "value": c.get("value"),
                "operator": c.get("operator"),
                "unit": c.get("unit"),
                "raw_text": c.get("raw_text"),
            }
            metrics.setdefault(key, []).append(entry)
        for k, v in props.items():
            if k in ("numeric_constraints", "description", "source_file", "fair", "source_excerpt"):
                continue
            if any(p in k.lower() for p in param_keys) or k in param_keys:
                metrics.setdefault(k, v if not isinstance(v, list) else v[-1])
    return metrics


def compare_technologies(
    technologies: List[str],
    parameters: Optional[List[str]] = None,
) -> Dict[str, Any]:
    store = get_store()
    facts = store.list_facts(limit=500)
    cmp_cfg = compare_defaults()
    params = parameters or cmp_cfg.get("default_parameters") or []
    numeric_keys = cmp_cfg.get("numeric_keys") or []

    comparison = {}
    for tech in technologies:
        tech_lower = tech.lower()
        related = [
            f for f in facts
            if tech_lower in f["subject"].lower() or tech_lower in f["object"].lower()
        ]
        by_year: Dict[str, int] = defaultdict(int)
        for f in related:
            yr = (f.get("properties") or {}).get("year")
            if yr:
                by_year[str(yr)] += 1
        comparison[tech] = {
            "facts_count": len(related),
            "geographies": list({f.get("geography") for f in related if f.get("geography")}),
            "verified_count": sum(1 for f in related if f.get("verification_status") == "verified"),
            "parameters": _extract_tech_metrics(related, params + numeric_keys),
            "by_year": dict(by_year),
            "key_relations": dict(Counter(f["relation"] for f in related).most_common(5)),
            "related_entities": list({
                f["object"] if tech_lower in f["subject"].lower() else f["subject"]
                for f in related
            })[:10],
        }

    try:
        with Neo4jLoader() as loader:
            for tech in technologies:
                neighbors = loader.search_neighbors(tech, depth=1)
                if tech in comparison:
                    comparison[tech]["graph_neighbors"] = len(neighbors)
    except Exception:
        pass

    return {
        "technologies": technologies,
        "comparison": comparison,
        "recommendation": _compare_recommendation(comparison),
    }


def _compare_recommendation(comparison: Dict) -> str:
    if not comparison:
        return "Недостаточно данных для сравнения."
    scored = []
    for name, data in comparison.items():
        param_count = len(data.get("parameters") or {})
        score = data["verified_count"] * 2 + data["facts_count"] + param_count
        scored.append((score, name, data))
    scored.sort(reverse=True)
    _, best_name, best = scored[0]
    param_note = ""
    if best.get("parameters"):
        param_note = f", {len(best['parameters'])} параметр(ов) в данных"
    return (
        f"Наиболее документированная технология: «{best_name}» "
        f"({best['verified_count']} verified, {best['facts_count']} фактов{param_note})."
    )
