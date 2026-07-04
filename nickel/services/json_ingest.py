"""Импорт JSON: готовые triples или массив терминов глоссария."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from services.store import get_store


def is_glossary_json(data: Any) -> bool:
    if isinstance(data, list):
        return bool(data) and isinstance(data[0], dict) and "canonical" in data[0]
    if isinstance(data, dict) and isinstance(data.get("glossary"), list):
        items = data["glossary"]
        return bool(items) and isinstance(items[0], dict) and "canonical" in items[0]
    return False


def import_glossary_json(data: Any, source: str = "upload") -> Dict[str, int]:
    store = get_store()
    terms = data if isinstance(data, list) else data.get("glossary", [])
    added = 0
    skipped = 0
    existing = {t["canonical"].lower() for t in store.iter_glossary()}
    for term in terms:
        if not isinstance(term, dict) or not term.get("canonical"):
            continue
        key = term["canonical"].strip().lower()
        if key in existing:
            skipped += 1
            continue
        store.add_glossary_term(term, source=source)
        existing.add(key)
        added += 1
    return {"terms_added": added, "terms_skipped": skipped, "terms_total": len(terms)}


def load_triples_json(data: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError("JSON with triples must be an object with a 'triples' array")
    triples = data.get("triples")
    if not isinstance(triples, list):
        raise ValueError("JSON must contain a 'triples' array")
    metadata = data.get("document_metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return triples, metadata


def parse_json_upload(filepath: str) -> Tuple[str, Any]:
    """Return ('glossary' | 'triples', payload)."""
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    if is_glossary_json(data):
        return "glossary", data

    triples, _ = load_triples_json(data)
    if not triples:
        raise ValueError(
            "JSON must contain a non-empty 'triples' array or glossary terms with 'canonical'"
        )
    return "triples", data


def load_json_file(filepath: str) -> Any:
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)
