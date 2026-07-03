"""Ручная правка графа экспертами."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ontology.schema import filter_valid_triples, is_valid_triple
from services.neo4j_loader import Neo4jLoader
from services.store import get_store


def add_triple(triple: Dict[str, Any], user_id: str, comment: str = "") -> Dict[str, Any]:
    if not is_valid_triple(triple):
        raise ValueError("Triple does not match ontology")
    triple.setdefault("verification_status", "verified")
    triple.setdefault("confidence", 0.9)

    store = get_store()
    store.upsert_facts(
        [triple],
        job_id=f"manual-{uuid.uuid4().hex[:8]}",
        source_document="expert_edit",
        shacl_valid=True,
        changed_by=user_id,
    )
    store.log_graph_edit(user_id, "add", None, triple, comment)

    try:
        with Neo4jLoader() as loader:
            loader.load_triples([triple], source_document="expert_edit")
    except Exception:
        pass

    return triple


def update_triple(
    fact_id: str,
    updates: Dict[str, Any],
    user_id: str,
    comment: str = "",
) -> Optional[Dict[str, Any]]:
    store = get_store()
    fact = store.get_fact(fact_id)
    if not fact:
        return None
    before = dict(fact)
    for key in ("subject", "object", "relation", "properties", "confidence", "geography", "notes"):
        if key in updates:
            fact[key] = updates[key]
    if updates.get("verification_status"):
        store.verify_fact(fact_id, updates["verification_status"], user_id, updates.get("notes", ""))
    store.log_graph_edit(user_id, "update", before, fact, comment)
    return fact


def delete_triple(fact_id: str, user_id: str, comment: str = "") -> bool:
    store = get_store()
    fact = store.get_fact(fact_id)
    if not fact:
        return False
    store.verify_fact(fact_id, "rejected", user_id, comment or "deleted by expert")
    store.log_graph_edit(user_id, "delete", fact, None, comment)
    return True


def list_edits(limit: int = 50) -> List[Dict]:
    return get_store().list_graph_edits(limit)
