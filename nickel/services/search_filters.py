"""Расширенные фильтры, comparative mode, обёртка над hybrid pipeline."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from services.glossary import expand_query_with_glossary, glossary_use_bge
from services.hybrid_search import hybrid_ranked_search
from services.language_detect import detect_query_language
from services.numeric_parser import parse_numeric_query
from services.numeric_query import search_by_numeric_query
from services.store import get_store


def filtered_search(
    query: str,
    limit: int = 10,
    entity_type: Optional[str] = None,
    geography: Optional[str] = None,
    min_confidence: Optional[float] = None,
    verification_status: Optional[str] = None,
    job_id: Optional[str] = None,
    year: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    author: Optional[str] = None,
    document_kind: Optional[str] = None,
    include_numeric: bool = True,
    use_hybrid: bool = True,
    graph_depth: int = 3,
    relation_filter: Optional[List[str]] = None,
    type_filter: Optional[List[str]] = None,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    if use_hybrid:
        result = hybrid_ranked_search(
            query,
            limit=limit,
            entity_type=entity_type,
            geography=geography,
            min_confidence=min_confidence,
            verification_status=verification_status,
            job_id=job_id,
            year=year,
            year_from=year_from,
            year_to=year_to,
            author=author,
            document_kind=document_kind,
            graph_depth=graph_depth,
            relation_filter=relation_filter,
            type_filter=type_filter,
            role=role,
        )
    else:
        from services.qdrant_index import QdrantIndexer

        lang = detect_query_language(query)
        glossary_expansion = expand_query_with_glossary(query, use_bge=glossary_use_bge())
        expanded = glossary_expansion["expanded"]
        indexer = QdrantIndexer()
        meta = {
            "document_kind": document_kind,
            "year": year,
            "year_from": year_from,
            "year_to": year_to,
            "author": author,
            "geography": geography,
        }
        chunks = indexer.search_chunks(expanded, limit=limit, job_id=job_id, metadata_filters=meta)
        entities = indexer.search_entities(expanded, entity_type=entity_type, limit=limit)
        facts = get_store().list_facts(
            status=verification_status,
            geography=geography,
            min_confidence=min_confidence,
            year=year,
            year_from=year_from,
            year_to=year_to,
            author=author,
            document_kind=document_kind,
            job_id=job_id,
            query=query,
            limit=limit * 5,
        )
        result = {
            "query": query,
            "detected_language": lang,
            "expanded_query": expanded if expanded != query else None,
            "glossary_matches": glossary_expansion.get("matched_terms", []),
            "filters_applied": {
                "entity_type": entity_type,
                "geography": geography,
                "min_confidence": min_confidence,
                "verification_status": verification_status,
                "year": year,
                "year_from": year_from,
                "year_to": year_to,
                "author": author,
                "document_kind": document_kind,
            },
            "chunks": chunks,
            "entities": entities,
            "verified_facts": facts[:limit],
            "ranked_results": [],
        }

    if include_numeric and parse_numeric_query(query):
        result["numeric_search"] = search_by_numeric_query(
            query,
            limit=limit,
            geography=geography,
            verification_status=verification_status,
        )
    if role:
        from services.access_control import filter_search_result
        result = filter_search_result(result, role, get_store().get_document_access_map())
    return result


def _topic_set(data: Dict[str, Any]) -> Set[str]:
    topics: Set[str] = set()
    for fact in data.get("verified_facts", []):
        topics.add(fact["subject"])
        topics.add(fact["object"])
    for entity in data.get("entities", []):
        if entity.get("name"):
            topics.add(entity["name"])
    return topics


def _facts_by_relation(facts: List[Dict]) -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = defaultdict(list)
    for f in facts:
        grouped[f.get("relation", "related")].append(f)
    return dict(grouped)


def compare_practices(
    query: str,
    limit: int = 10,
    min_confidence: Optional[float] = None,
    document_kind: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    author: Optional[str] = None,
) -> Dict[str, Any]:
    """Режим «отечественная vs мировая практика»: параллельный hybrid-поиск RU vs EN/global."""
    shared_filters = {
        "limit": limit,
        "min_confidence": min_confidence,
        "document_kind": document_kind,
        "year_from": year_from,
        "year_to": year_to,
        "author": author,
    }

    domestic = hybrid_ranked_search(query, geography="RU", **shared_filters)
    global_en = hybrid_ranked_search(query, geography="EN", **shared_filters)
    global_world = hybrid_ranked_search(query, geography="global", **shared_filters)

    ru_topics = _topic_set(domestic)
    en_topics = _topic_set(global_en) | _topic_set(global_world)
    shared = ru_topics & en_topics
    ru_only = sorted(ru_topics - en_topics)[:15]
    global_only = sorted(en_topics - ru_topics)[:15]

    ru_facts = domestic.get("verified_facts", [])
    global_facts = (global_en.get("verified_facts", []) + global_world.get("verified_facts", []))

    ru_methods = _facts_by_relation(ru_facts)
    global_methods = _facts_by_relation(global_facts)

    method_gaps = []
    for rel, ru_items in ru_methods.items():
        global_items = global_methods.get(rel, [])
        if ru_items and not global_items:
            method_gaps.append({"relation": rel, "gap": "ru_only", "ru_count": len(ru_items)})
        elif global_items and not ru_items:
            method_gaps.append({"relation": rel, "gap": "global_only", "global_count": len(global_items)})

    summary_parts = [
        f"Сравнение практик по запросу «{query}».",
        f"Отечественная (RU): {len(ru_facts)} фактов, {len(domestic.get('ranked_results', []))} ranked hits.",
        f"Мировая (EN/global): {len(global_facts)} фактов.",
    ]
    if ru_only:
        summary_parts.append(f"Только в RU: {', '.join(ru_only[:5])}.")
    if global_only:
        summary_parts.append(f"Только в мировой практике: {', '.join(global_only[:5])}.")
    if shared:
        summary_parts.append(f"Общие темы: {', '.join(sorted(shared)[:5])}.")

    return {
        "query": query,
        "mode": "domestic_vs_global",
        "domestic": {
            "label": "Отечественная практика (RU)",
            "geography": "RU",
            **domestic,
        },
        "global": {
            "label": "Мировая практика (EN + global)",
            "geographies": ["EN", "global"],
            "ranked_results": sorted(
                (global_en.get("ranked_results", []) + global_world.get("ranked_results", [])),
                key=lambda x: x.get("score", 0),
                reverse=True,
            )[:limit],
            "verified_facts": global_facts[:limit],
            "entities": (global_en.get("entities", []) + global_world.get("entities", []))[:limit],
            "chunks": (global_en.get("chunks", []) + global_world.get("chunks", []))[:limit],
        },
        "comparison": {
            "shared_topics": sorted(shared)[:20],
            "ru_only_topics": ru_only,
            "global_only_topics": global_only,
            "method_gaps": method_gaps[:15],
            "ru_methods": {k: len(v) for k, v in ru_methods.items()},
            "global_methods": {k: len(v) for k, v in global_methods.items()},
            "summary": " ".join(summary_parts),
        },
    }
