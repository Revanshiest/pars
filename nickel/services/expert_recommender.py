"""Рекомendации экспертов с fallback при отсутствии Expert в графе."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Set

from services.glossary import expand_query_with_glossary, glossary_use_bge
from services.neo4j_loader import Neo4jLoader
from services.search_filters import filtered_search
from services.store import get_store


def _topic_terms(topic: str) -> Set[str]:
    terms = {topic.lower()}
    try:
        g = expand_query_with_glossary(topic, use_bge=glossary_use_bge())
        terms.add(g.get("expanded", topic).lower())
        terms.update(s.lower() for s in g.get("synonyms_added", []))
    except Exception:
        pass
    return terms


def _matches_topic(text: str, terms: Set[str]) -> bool:
    t = text.lower()
    return any(term in t for term in terms if len(term) > 2)


def recommend_experts(topic: str, limit: int = 10) -> Dict[str, Any]:
    store = get_store()
    terms = _topic_terms(topic)
    data = filtered_search(topic, limit=15)
    facts = store.list_facts(limit=500)
    topic_facts = [
        f for f in facts
        if _matches_topic(f["subject"], terms) or _matches_topic(f["object"], terms)
    ]

    candidates: Dict[str, Dict[str, Any]] = {}

    def add(name: str, source: str, score: float = 0.5, **extra):
        name = name.strip()
        if not name or len(name) < 3:
            return
        key = name.lower()
        if key not in candidates or candidates[key]["score"] < score:
            candidates[key] = {"name": name, "source": source, "score": score, **extra}
        else:
            candidates[key]["score"] = min(1.0, candidates[key]["score"] + 0.05)

    for f in facts:
        if f["subject_type"] == "Expert":
            add(f["subject"], "expert_node", 0.95, context=f["object"], relation=f["relation"])
        if f["object_type"] == "Expert":
            add(f["object"], "expert_node", 0.95, context=f["subject"], relation=f["relation"])

    for e in data.get("entities", []):
        if e.get("type") == "Expert":
            add(e["name"], "expert_entity", 0.9, semantic_score=e.get("score"))

    for f in facts:
        if f["relation"] == "managed_by":
            expert = f["object"] if f["object_type"] == "Expert" else f["subject"]
            facility = f["subject"] if f["object_type"] == "Expert" else f["object"]
            if _matches_topic(facility, terms) or _matches_topic(expert, terms):
                add(expert, "managed_by", 0.85, facility=facility)

    doc_authors: Counter = Counter()
    doc_index = {d["source_document"]: d for d in store.list_documents(limit=300)}
    for f in topic_facts:
        author = (f.get("properties") or {}).get("author")
        if author:
            doc_authors[author] += 1
        src = f.get("source_document")
        if src and src in doc_index and doc_index[src].get("author"):
            doc_authors[doc_index[src]["author"]] += 2

    for author, cnt in doc_authors.most_common(8):
        add(author, "document_author", min(0.8, 0.5 + 0.05 * cnt), publications=cnt)

    for u in store.list_users():
        blob = f"{u.get('name', '')} {u.get('email', '')}".lower()
        if _matches_topic(blob, terms):
            score = 0.75 if u.get("role") == "analyst" else 0.6
            add(u["name"], "platform_user", score, email=u.get("email"), role=u.get("role"))

    try:
        with Neo4jLoader() as loader:
            for entity in data.get("entities", [])[:5]:
                if entity.get("type") == "Expert":
                    continue
                for row in loader.search_neighbors(entity.get("name", ""), depth=2):
                    target = row.get("target") or row.get("object", "")
                    if target:
                        add(target, "graph_neighbor", 0.55, via=entity.get("name"))
    except Exception:
        pass

    process_leads: Dict[str, int] = defaultdict(int)
    for f in topic_facts:
        if f.get("verification_status") == "verified" and (f.get("confidence") or 0) >= 0.7:
            for side in ("subject", "object"):
                if f[f"{side}_type"] in ("Facility", "Process", "Experiment"):
                    process_leads[f[side]] += 1

    for proc, cnt in sorted(process_leads.items(), key=lambda x: -x[1])[:5]:
        add(
            f"Специалист по «{proc}»",
            "inferred_from_process",
            0.45,
            note="Expert не извлечён — рекомендуется отраслевой эксперт",
            related_process=proc,
        )

    ranked = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)[:limit]
    has_explicit = any(e["source"] in ("expert_node", "expert_entity") for e in ranked)

    return {
        "topic": topic,
        "experts": ranked,
        "experts_count": len(ranked),
        "has_explicit_experts": has_explicit,
        "fallback_used": not has_explicit and len(ranked) > 0,
    }
