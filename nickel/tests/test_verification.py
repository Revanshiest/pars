"""Unit-тесты верификации и provenance."""

from __future__ import annotations

from services.verification import (
    build_provenance,
    credibility_tier,
    source_kind,
)


def test_source_kind_publication():
    fact = {"properties": {"document_kind": "publication"}}
    assert source_kind(fact) == "publication"


def test_credibility_verified_boost():
    fact = {
        "confidence": 0.8,
        "verification_status": "verified",
        "properties": {"document_kind": "publication", "doi": "10.1234/x"},
    }
    tier = credibility_tier(fact)
    assert tier["tier"] in ("high", "medium")
    assert tier["verified"] is True


def test_provenance_fields():
    fact = {
        "source_document": "report.pdf",
        "properties": {"page": 12, "year": 2024, "author": "Ivanov"},
    }
    prov = build_provenance(fact)
    assert prov["source_document"] == "report.pdf"
    assert prov["year"] == 2024
