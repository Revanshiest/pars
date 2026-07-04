"""Рекомendации экспертов на основе графа, документов и авторов."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Set

from services.glossary import expand_query_with_glossary
from services.neo4j_loader import Neo4jLoader
from services.platform_config import verification_policy
from services.search_filters import filtered_search
from services.store import get_store

_EXPLICIT_SOURCES = frozenset({"expert_node", "expert_entity", "managed_by"})


def _topic_terms(topic: str) -> Set[str]:
    terms = {topic.lower()}
    try:
        g = expand_query_with_glossary(topic, use_bge=True)
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
    min_conf = float(verification_policy().get("expert_min_confidence", 0.7))
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
        if source == "graph_neighbor" and name.lower() in terms:
            return
        key = name.lower()
        if key not in candidates or candidates[key]["score"] < score:
            candidates[key] = {"name": name, "source": source, "score": round(score, 3), **extra}
        else:
            candidates[key]["score"] = round(min(1.0, candidates[key]["score"] + 0.05), 3)

    for f in facts:
        if f["subject_type"] == "Expert":
            if _matches_topic(f["object"], terms) or _matches_topic(f["subject"], terms):
                add(f["subject"], "expert_node", 0.95, context=f["object"], relation=f["relation"])
        if f["object_type"] == "Expert":
            if _matches_topic(f["subject"], terms) or _matches_topic(f["object"], terms):
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

    try:
        with Neo4jLoader() as loader:
            for entity in data.get("entities", [])[:5]:
                if entity.get("type") == "Expert":
                    continue
                ename = entity.get("name", "")
                if not ename or not _matches_topic(ename, terms):
                    continue
                for row in loader.search_neighbors(ename, depth=2):
                    target = row.get("target") or row.get("object", "")
                    rel = row.get("relation", "")
                    if target and rel in ("managed_by", "validated_by"):
                        add(target, "graph_neighbor", 0.6, via=ename, relation=rel)
    except Exception:
        pass

    related_processes: List[str] = []
    for f in topic_facts:
        if f.get("verification_status") == "verified" and (f.get("confidence") or 0) >= min_conf:
            for side in ("subject", "object"):
                if f[f"{side}_type"] in ("Facility", "Process", "Experiment"):
                    related_processes.append(f[side])

    ranked = sorted(candidates.values(), key=lambda x: x["score"], reverse=True)[:limit]
    has_explicit = any(e["source"] in _EXPLICIT_SOURCES for e in ranked)
    has_authors_only = bool(ranked) and not has_explicit and all(
        e["source"] == "document_author" for e in ranked
    )

    return {
        "topic": topic,
        "experts": ranked,
        "experts_count": len(ranked),
        "has_explicit_experts": has_explicit,
        "fallback_used": has_authors_only,
        "related_processes": list(dict.fromkeys(related_processes))[:8],
        "message": (
            None if ranked else
            "В графе нет узлов Expert по теме. Добавьте экспертов через редактор графа "
            "или загрузите каталог сотрудников."
        ),
    }
