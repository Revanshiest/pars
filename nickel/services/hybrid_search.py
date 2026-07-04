"""Единый ranked pipeline: vector search + graph traversal + facts."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from services.glossary import expand_query_with_glossary, glossary_use_bge
from services.language_detect import detect_query_language, merge_search_results
from services.neo4j_loader import Neo4jLoader
from services.store import get_store

SOURCE_WEIGHTS = {
    "chunk": 1.0,
    "entity": 0.88,
    "fact": 0.78,
    "graph_edge": 0.68,
}
GRAPH_BOOST = 0.12


def search_use_vectors() -> bool:
    return os.getenv("SEARCH_USE_VECTORS", "false").lower() in ("1", "true", "yes")


def search_use_graph_boost() -> bool:
    return os.getenv("SEARCH_USE_GRAPH", "false").lower() in ("1", "true", "yes")


def _result_key(item: Dict[str, Any]) -> Tuple[str, str]:
    return (item.get("result_type", ""), item.get("id", ""))


def _graph_edge_id(row: Dict[str, Any]) -> str:
    return f"{row.get('source', row.get('subject', ''))}:{row.get('relation', '')}:{row.get('target', row.get('object', ''))}"


def hybrid_ranked_search(
    query: str,
    limit: int = 20,
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
    graph_depth: int = 2,
    graph_entity_limit: int = 5,
    role: Optional[str] = None,
) -> Dict[str, Any]:
    lang = detect_query_language(query)
    glossary = expand_query_with_glossary(query, use_bge=glossary_use_bge())
    expanded = glossary["expanded"]

    meta_filters = {
        "document_kind": document_kind,
        "year": year,
        "year_from": year_from,
        "year_to": year_to,
        "author": author,
        "geography": geography,
    }

    store = get_store()
    search_limit = min(limit * 3, 60)
    chunks: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []

    if search_use_vectors():
        try:
            from services.qdrant_index import QdrantIndexer

            indexer = QdrantIndexer()
            chunks = indexer.search_chunks(
                expanded, limit=search_limit, job_id=job_id, metadata_filters=meta_filters
            )
            if lang in ("en", "mixed"):
                extra = indexer.search_chunks(
                    query, limit=search_limit, job_id=job_id, metadata_filters=meta_filters
                )
                chunks = merge_search_results(chunks, extra, key_fn=lambda x: x.get("chunk_id"), limit=search_limit)

            entities = indexer.search_entities(expanded, entity_type=entity_type, limit=search_limit)
            if lang in ("en", "mixed"):
                extra_e = indexer.search_entities(query, entity_type=entity_type, limit=search_limit)
                entities = merge_search_results(entities, extra_e, key_fn=lambda x: x.get("name"), limit=search_limit)
        except Exception:
            pass

    facts = store.list_facts(
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
        limit=search_limit,
        role=role,
    )

    ranked: Dict[Tuple[str, str], Dict[str, Any]] = {}
    entity_names_in_graph: Set[str] = set()

    for chunk in chunks:
        score = float(chunk.get("score", 0)) * SOURCE_WEIGHTS["chunk"]
        rid = chunk.get("chunk_id") or chunk.get("document", "")
        ranked[_result_key({"result_type": "chunk", "id": rid})] = {
            "result_type": "chunk",
            "id": rid,
            "score": score,
            "title": chunk.get("document", "document"),
            "snippet": (chunk.get("text") or "")[:400],
            "metadata": {
                "document": chunk.get("document"),
                "chunk_id": chunk.get("chunk_id"),
                "headers": chunk.get("headers"),
                "document_kind": chunk.get("document_kind"),
                "year": chunk.get("year"),
                "author": chunk.get("author"),
                "geography": chunk.get("geography"),
            },
            "sources": ["vector"],
            "raw": chunk,
        }

    for entity in entities:
        score = float(entity.get("score", 0)) * SOURCE_WEIGHTS["entity"]
        name = entity.get("name", "")
        ranked[_result_key({"result_type": "entity", "id": name})] = {
            "result_type": "entity",
            "id": name,
            "score": score,
            "title": name,
            "snippet": f"{entity.get('type', 'Entity')} — semantic match",
            "metadata": {"type": entity.get("type"), "name": name},
            "sources": ["vector"],
            "raw": entity,
        }

    for fact in facts:
        fid = fact.get("id") or fact.get("fact_id", "")
        conf = fact.get("confidence") or 0.5
        text_match = 0.15 if query.lower() in fact["subject"].lower() or query.lower() in fact["object"].lower() else 0.0
        score = (0.55 + 0.35 * conf + text_match) * SOURCE_WEIGHTS["fact"]
        ranked[_result_key({"result_type": "fact", "id": fid})] = {
            "result_type": "fact",
            "id": fid,
            "score": score,
            "title": f"{fact['subject']} —[{fact['relation']}]→ {fact['object']}",
            "snippet": str((fact.get("properties") or {}))[:300],
            "metadata": {
                "geography": fact.get("geography"),
                "confidence": fact.get("confidence"),
                "verification_status": fact.get("verification_status"),
                "source_document": fact.get("source_document"),
                "year": (fact.get("properties") or {}).get("year"),
                "author": (fact.get("properties") or {}).get("author"),
                "document_kind": (fact.get("properties") or {}).get("document_kind"),
            },
            "sources": ["sqlite"],
            "raw": fact,
        }

    try:
        if search_use_graph_boost() and entities:
            with Neo4jLoader() as loader:
                for entity in entities[:graph_entity_limit]:
                    name = entity.get("name")
                    if not name:
                        continue
                    neighbors = loader.search_neighbors(name, depth=graph_depth)
                    entity_score = float(entity.get("score", 0.5))
                    for row in neighbors:
                        eid = _graph_edge_id(row)
                        key = _result_key({"result_type": "graph_edge", "id": eid})
                        edge_score = entity_score * SOURCE_WEIGHTS["graph_edge"]
                        if key in ranked:
                            ranked[key]["score"] += GRAPH_BOOST
                            if "graph" not in ranked[key]["sources"]:
                                ranked[key]["sources"].append("graph")
                        else:
                            ranked[key] = {
                                "result_type": "graph_edge",
                                "id": eid,
                                "score": edge_score,
                                "title": f"{row.get('source', '?')} → {row.get('target', '?')}",
                                "snippet": f"relation: {row.get('relation', row.get('target_type', 'REL'))}",
                                "metadata": row,
                                "sources": ["graph"],
                                "raw": row,
                            }
                        entity_names_in_graph.add(name)
    except Exception:
        pass

    for key, item in ranked.items():
        if item["result_type"] == "entity" and item["id"] in entity_names_in_graph:
            item["score"] += GRAPH_BOOST
            if "graph" not in item["sources"]:
                item["sources"].append("graph")

    results = sorted(ranked.values(), key=lambda x: x["score"], reverse=True)[:limit]

    payload = {
        "query": query,
        "expanded_query": expanded if expanded != query else None,
        "detected_language": lang,
        "glossary_matches": glossary.get("matched_terms", []),
        "pipeline": "sqlite_text" if not search_use_vectors() else "hybrid_vector_graph",
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
            "job_id": job_id,
        },
        "ranked_results": results,
        "counts": {
            "chunks": len(chunks),
            "entities": len(entities),
            "facts": len(facts),
            "total_ranked": len(results),
        },
        "chunks": chunks[:limit],
        "entities": entities[:limit],
        "verified_facts": facts[:limit],
    }
    if role:
        from services.access_control import filter_search_result
        return filter_search_result(payload, role, store.get_document_access_map())
    return payload
