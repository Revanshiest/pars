"""Домен аудита: журнал действий (audit_log) и история правок графа (graph_edits)."""

from __future__ import annotations

import json
import uuid
from typing import Dict, List, Optional


class AuditMixin:
    """Методы работы с audit_log и graph_edits.

    Рассчитан на композицию в PlatformStore: использует self._lock,
    self._connect() и self._now() из базового хранилища.
    """

    def audit(self, user: Optional[Dict], action: str, resource: str = "", details: Optional[dict] = None, ip: str = ""):
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO audit_log (id, user_id, user_role, action, resource, details, ip, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    user["id"] if user else None,
                    user["role"] if user else None,
                    action,
                    resource,
                    json.dumps(details or {}, ensure_ascii=False),
                    ip,
                    self._now(),
                ),
            )

    def log_graph_edit(self, user_id: str, action: str, before: Optional[dict], after: Optional[dict], comment: str = ""):
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO graph_edits (id, user_id, action, before_state, after_state, comment, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), user_id, action,
                    json.dumps(before, ensure_ascii=False) if before else None,
                    json.dumps(after, ensure_ascii=False) if after else None,
                    comment, self._now(),
                ),
            )

    def list_graph_edits(self, limit: int = 50) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM graph_edits ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("before_state"):
                    d["before_state"] = json.loads(d["before_state"])
                if d.get("after_state"):
                    d["after_state"] = json.loads(d["after_state"])
                result.append(d)
            return result

    def audit_log_list(self, limit: int = 100) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["details"] = json.loads(d["details"]) if d.get("details") else {}
                result.append(d)
            return result
