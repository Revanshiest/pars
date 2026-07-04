"""Тесты импорта JSON (глоссарий и triples)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.json_ingest import import_glossary_json, is_glossary_json, load_triples_json, parse_json_upload


def test_is_glossary_json_array():
    data = [{"canonical": "никель", "synonyms_ru": [], "synonyms_en": ["nickel"]}]
    assert is_glossary_json(data) is True


def test_is_glossary_json_wrapped():
    data = {"glossary": [{"canonical": "медь", "synonyms_ru": [], "synonyms_en": []}]}
    assert is_glossary_json(data) is True


def test_is_glossary_json_triples():
    data = {"triples": [{"subject": "A", "relation": "related_to", "object": "B"}]}
    assert is_glossary_json(data) is False


def test_import_glossary_json(tmp_platform_db):
    from services.store import get_store

    payload = [
        {
            "canonical": "тестовый термин",
            "synonyms_ru": ["синоним"],
            "synonyms_en": ["test term"],
            "domain": "Concept",
            "definition": "Для теста",
        }
    ]
    stats = import_glossary_json(payload)
    assert stats["terms_added"] == 1
    terms = get_store().list_glossary(q="тестовый")
    assert any(t["canonical"] == "тестовый термин" for t in terms)


def test_load_triples_json():
    data = {
        "document_metadata": {"document_kind": "report", "label": "Report"},
        "triples": [
            {
                "subject": "никель",
                "subject_type": "Material",
                "relation": "related_to",
                "object": "медь",
                "object_type": "Material",
            }
        ],
    }
    triples, meta = load_triples_json(data)
    assert len(triples) == 1
    assert meta["document_kind"] == "report"


def test_parse_json_upload_glossary(tmp_path):
    path = tmp_path / "glossary.json"
    path.write_text(
        json.dumps([{"canonical": "шлак", "synonyms_ru": [], "synonyms_en": ["slag"]}]),
        encoding="utf-8",
    )
    kind, _ = parse_json_upload(str(path))
    assert kind == "glossary"


def test_parse_json_upload_triples(tmp_path):
    path = tmp_path / "graph.json"
    path.write_text(
        json.dumps({"triples": [{"subject": "A", "subject_type": "Material", "relation": "related_to", "object": "B", "object_type": "Material"}]}),
        encoding="utf-8",
    )
    kind, _ = parse_json_upload(str(path))
    assert kind == "triples"
