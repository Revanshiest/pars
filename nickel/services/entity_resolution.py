"""Entity resolution — перенос логики post_processor в API-пайплайн."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from langchain_community.embeddings import HuggingFaceEmbeddings
import numpy as np
from sklearn.cluster import AgglomerativeClustering


async def resolve_entities(triples: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not triples:
        return [], {"input": 0, "output": 0, "clusters": 0, "quarantine": 0}

    quarantine = []
    unique_entities: set[str] = set()
    valid_triples = []

    for t in triples:
        subj = str(t.get("subject", "")).strip()
        obj = str(t.get("object", "")).strip()
        if len(subj) > 100 or len(obj) > 100:
            quarantine.append({"triple": t, "reason": "node_too_long"})
            continue
        if subj:
            unique_entities.add(subj)
        if obj:
            unique_entities.add(obj)
        valid_triples.append(t)

    mapping = await _build_entity_mapping(list(unique_entities))

    cleaned = []
    seen = set()
    for t in valid_triples:
        subj = mapping.get(str(t.get("subject", "")).strip(), t.get("subject"))
        obj = mapping.get(str(t.get("object", "")).strip(), t.get("object"))
        props = t.get("properties") or {}
        key = f"{subj}|{t.get('relation')}|{obj}|{json.dumps(props, sort_keys=True)}"
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({**t, "subject": subj, "object": obj})

    stats = {
        "input": len(triples),
        "output": len(cleaned),
        "unique_entities": len(unique_entities),
        "clusters": len(set(mapping.values())),
        "quarantine": len(quarantine),
        "merged_entities": sum(1 for k, v in mapping.items() if k != v),
    }
    return cleaned, stats


async def _build_entity_mapping(unique_entities: List[str]) -> Dict[str, str]:
    if not unique_entities:
        return {}
    if len(unique_entities) == 1:
        return {unique_entities[0]: unique_entities[0]}

    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    try:
        vectors = embeddings.embed_documents(unique_entities)
    except Exception:
        return {term: term for term in unique_entities}

    X = np.array(vectors)
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="cosine",
        linkage="average",
        distance_threshold=0.05,
    )
    labels = clustering.fit_predict(X)

    clusters: Dict[int, List[str]] = {}
    for term, label in zip(unique_entities, labels):
        clusters.setdefault(label, []).append(term)

    mapping = {}
    for terms in clusters.values():
        canonical = sorted(terms, key=len)[0]
        for term in terms:
            mapping[term] = canonical
    return mapping
