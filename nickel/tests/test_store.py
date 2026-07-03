"""Unit-тесты PlatformStore."""

from __future__ import annotations


def test_create_user_and_auth(tmp_platform_db):
    store = tmp_platform_db
    created = store.create_user("admin@test.local", "Admin", "admin")
    assert created["role"] == "admin"
    key = created["api_key"]
    assert len(key) >= 32

    found = store.get_user_by_key(key)
    assert found["email"] == "admin@test.local"


def test_role_permissions(tmp_platform_db):
    store = tmp_platform_db
    assert store.has_permission("analyst", "export")
    assert store.has_permission("admin", "verify")
    assert not store.has_permission("external_partner", "upload")
    assert store.has_permission("admin", "anything")


def test_glossary_seed(tmp_platform_db):
    store = tmp_platform_db
    from pathlib import Path

    seed = Path(__file__).resolve().parent.parent / "ontology" / "glossary_seed.json"
    if seed.exists():
        store.seed_glossary_from_file(seed)
        terms = store.list_glossary()
        assert len(terms) >= 1
