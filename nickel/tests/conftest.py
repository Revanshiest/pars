"""Pytest fixtures: изолированная SQLite БД."""

from __future__ import annotations

import os
import tempfile

import pytest


AUTH_TEST_KEY = "test-admin-key-minimum-16-chars!!"


@pytest.fixture()
def tmp_platform_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("PLATFORM_DB", path)
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-minimum-32-characters!!")
    monkeypatch.setenv("SKIP_OLLAMA_HEALTH", "true")
    monkeypatch.setenv("AUTH_ADMIN", f"admin@test.local|Admin|{AUTH_TEST_KEY}")

    import services.store as store_mod

    store_mod._store = None
    store = store_mod.get_store()
    yield store
    store_mod._store = None
    try:
        os.unlink(path)
    except OSError:
        pass
