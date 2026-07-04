"""Tests for lightweight search and JSON fast import."""

from __future__ import annotations

import json
from pathlib import Path


def test_hybrid_search_sqlite_only(tmp_platform_db, monkeypatch):
    monkeypatch.setenv("GLOSSARY_USE_BGE", "false")
    monkeypatch.setenv("SEARCH_USE_VECTORS", "false")
    monkeypatch.setenv("SEARCH_USE_GRAPH", "false")

    from services.auth_bootstrap import bootstrap_admin_from_env
    from services.hybrid_search import hybrid_ranked_search
    from services.store import get_store

    bootstrap_admin_from_env()
    store = get_store()
    store.upsert_facts(
        [{
            "subject": "copper ore",
            "subject_type": "Material",
            "relation": "processed_by",
            "object": "heap leaching",
            "object_type": "Process",
            "confidence": 0.9,
        }],
        job_id="test-job",
        source_document="test-doc",
    )

    result = hybrid_ranked_search("copper", limit=5, role="admin")
    assert result["pipeline"] == "sqlite_text"
    assert result["counts"]["facts"] >= 1
    assert len(result["ranked_results"]) >= 1


def test_import_triples_json_file(tmp_platform_db, monkeypatch):
    monkeypatch.setenv("INDEX_QDRANT_ON_IMPORT", "false")

    from services.json_graph_import import import_triples_json_file
    from services.store import get_store

    payload = {
        "document_metadata": {"document_kind": "report", "title": "demo-json"},
        "triples": [
            {
                "subject": "nickel",
                "subject_type": "Material",
                "relation": "related_to",
                "object": "copper",
                "object_type": "Material",
            }
        ],
    }
    path = Path(tmp_platform_db.db_path).parent / "demo.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = import_triples_json_file(str(path), job_id="job-demo")
    assert result["triples_count"] == 1
    facts = get_store().list_facts(source_document="demo-json", limit=10)
    assert len(facts) == 1
