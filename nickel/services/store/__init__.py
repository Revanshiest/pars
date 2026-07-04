"""Единое SQLite-хранилище: пользователи, глоссарий, верификация, аудит, уведомления."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.store import schema
from services.store.audit import AuditMixin
from services.store.documents import DocumentsMixin
from services.store.facts import FactsMixin
from services.store.glossary import GlossaryMixin
from services.store.notifications import NotificationsMixin
from services.store.users import ROLE_PERMISSIONS, ROLES, UsersMixin

__all__ = ["PlatformStore", "get_store", "ROLES", "ROLE_PERMISSIONS"]


class PlatformStore(
    AuditMixin,
    DocumentsMixin,
    FactsMixin,
    GlossaryMixin,
    NotificationsMixin,
    UsersMixin,
):
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("PLATFORM_DB", "data/platform.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._glossary_index_cache: Optional[Dict[str, str]] = None
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            schema.create_schema(conn)
            schema.migrate_schema(conn)
            schema.create_late_indexes(conn)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def dashboard_metrics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            facts_total = conn.execute("SELECT COUNT(*) AS c FROM verified_facts").fetchone()["c"]
            verified = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='verified'"
            ).fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='pending'"
            ).fetchone()["c"]
            assigned_pending = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='pending' AND assigned_to IS NOT NULL"
            ).fetchone()["c"]
            contradictions = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE relation='contradicts'"
            ).fetchone()["c"]
            glossary_count = conn.execute("SELECT COUNT(*) AS c FROM glossary").fetchone()["c"]
            by_domain = conn.execute(
                "SELECT domain, COUNT(*) AS c FROM glossary GROUP BY domain"
            ).fetchall()
            by_geo = conn.execute(
                "SELECT geography, COUNT(*) AS c FROM verified_facts WHERE geography IS NOT NULL GROUP BY geography"
            ).fetchall()
            by_type = conn.execute(
                "SELECT subject_type, COUNT(*) AS c FROM verified_facts GROUP BY subject_type ORDER BY c DESC"
            ).fetchall()
            low_coverage = conn.execute(
                """SELECT subject_type, COUNT(*) AS c FROM verified_facts
                   GROUP BY subject_type HAVING c < 5"""
            ).fetchall()
        return {
            "facts_total": facts_total,
            "verified": verified,
            "pending_verification": pending,
            "assigned_in_queue": assigned_pending,
            "contradictions": contradictions,
            "glossary_terms": glossary_count,
            "glossary_by_domain": {r["domain"]: r["c"] for r in by_domain},
            "facts_by_geography": {r["geography"]: r["c"] for r in by_geo},
            "facts_by_entity_type": {r["subject_type"]: r["c"] for r in by_type},
            "risk_zones_low_coverage": [dict(r) for r in low_coverage],
        }


_store: Optional[PlatformStore] = None


def get_store() -> PlatformStore:
    global _store
    if _store is None:
        _store = PlatformStore()
    return _store
