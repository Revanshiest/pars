"""Unit-тесты ACL."""

from __future__ import annotations

from services.access_control import can_access_level, filter_facts


def test_external_partner_access():
    assert can_access_level("external_partner", "public")
    assert can_access_level("external_partner", "partner")
    assert not can_access_level("external_partner", "internal")


def test_filter_facts_for_partner():
    facts = [
        {"subject": "A", "source_document": "pub.pdf"},
        {"subject": "B", "source_document": "secret.pdf"},
    ]
    doc_access = {"pub.pdf": "partner", "secret.pdf": "internal"}
    filtered = filter_facts(facts, "external_partner", doc_access)
    assert len(filtered) == 1
    assert filtered[0]["subject"] == "A"
