"""Unit-тесты health checks (без FastAPI)."""

from __future__ import annotations

from services.health import check_liveness, is_degraded_ok


def test_liveness():
    assert check_liveness()["status"] == "ok"


def test_degraded_sqlite_features(tmp_platform_db):
    assert is_degraded_ok("glossary")
    assert is_degraded_ok("export_md")
