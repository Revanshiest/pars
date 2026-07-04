"""Tests for hybrid search."""

from __future__ import annotations

import os

import pytest


def test_hybrid_search_no_unbound_local_error(tmp_platform_db, monkeypatch):
    monkeypatch.setenv("GLOSSARY_USE_BGE", "false")
    monkeypatch.setenv("SKIP_OLLAMA_HEALTH", "true")
    from services.auth_bootstrap import bootstrap_admin_from_env
    from services.store import get_store

    bootstrap_admin_from_env()
    store = get_store()
    store.add_glossary_term(
        {
            "canonical": "copper leaching",
            "synonyms_ru": ["выщелачивание меди"],
            "synonyms_en": [],
            "domain": "Process",
        }
    )
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

    from services.hybrid_search import hybrid_ranked_search

    result = hybrid_ranked_search("copper", limit=5, role="admin")
    assert result["query"] == "copper"
    assert isinstance(result["ranked_results"], list)
    assert result["counts"]["facts"] >= 1
