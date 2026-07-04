"""Подсчёт сущностей графа из triples / facts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from services.store import get_store


def entity_key(name: str, entity_type: str | None) -> Tuple[str, str]:
    return (name.strip(), (entity_type or "Concept").strip())


def count_unique_entities_from_triples(
    triples: Iterable[Dict[str, Any]],
    glossary_index: Optional[Dict[str, str]] = None,
) -> int:
    from services.glossary import normalize_entity

    index = glossary_index or get_store().build_glossary_index()
    seen: Set[str] = set()
    for t in triples:
        for name in (t.get("subject"), t.get("object")):
            if name:
                seen.add(normalize_entity(str(name).strip(), index=index).lower())
    return len(seen)


def summarize_import(triples: List[Dict[str, Any]]) -> Dict[str, int]:
    entities = count_unique_entities_from_triples(triples)
    return {
        "triples_count": len(triples),
        "entities_count": entities,
        "facts_count": len(triples),
    }
