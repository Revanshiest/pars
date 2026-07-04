"""Подсчёт сущностей графа из triples / facts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set, Tuple


def entity_key(name: str, entity_type: str | None) -> Tuple[str, str]:
    return (name.strip(), (entity_type or "Concept").strip())


def count_unique_entities_from_triples(triples: Iterable[Dict[str, Any]]) -> int:
    seen: Set[Tuple[str, str]] = set()
    for t in triples:
        subj, obj = t.get("subject"), t.get("object")
        if subj:
            seen.add(entity_key(str(subj), t.get("subject_type")))
        if obj:
            seen.add(entity_key(str(obj), t.get("object_type")))
    return len(seen)


def summarize_import(triples: List[Dict[str, Any]]) -> Dict[str, int]:
    entities = count_unique_entities_from_triples(triples)
    return {
        "triples_count": len(triples),
        "entities_count": entities,
        "facts_count": len(triples),
    }
