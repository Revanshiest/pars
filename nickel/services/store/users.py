"""Домен пользователей: учётки, роли, API-ключи, права и статус авторизации."""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


ROLES = ["researcher", "analyst", "project_manager", "admin", "external_partner"]

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "researcher": ["read", "search", "upload", "subscribe", "glossary_read", "dashboard"],
    "analyst": ["read", "search", "upload", "verify", "edit_graph", "export", "subscribe", "glossary_read", "glossary_write", "synthesis", "dashboard"],
    "project_manager": ["read", "search", "upload", "verify", "edit_graph", "export", "dashboard", "compare", "subscribe", "glossary_read", "synthesis", "audit"],
    "admin": ["*"],
    "external_partner": ["read", "search", "glossary_read"],
}


class UsersMixin:
    """Пользователи, роли, API-ключи и права. Композируется в PlatformStore
    (использует self._lock, self._connect(), self._now())."""

    @staticmethod
    def _api_key_expires_at() -> str:
        days = int(os.getenv("API_KEY_TTL_DAYS", "90"))
        exp = datetime.now(timezone.utc) + timedelta(days=days)
        return exp.isoformat()

    def count_users(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]

    def count_admins(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
            ).fetchone()["c"]

    def create_user(
        self,
        email: str,
        name: str,
        role: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError("Invalid email")
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Allowed: {ROLES}")

        key = (api_key or self._generate_api_key()).strip()
        if len(key) < 16:
            raise ValueError("API key must be at least 16 characters")

        uid = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise ValueError(f"Email already registered: {email}")
            conn.execute(
                "INSERT INTO users (id, email, name, role, created_at) VALUES (?,?,?,?,?)",
                (uid, email, name.strip(), role, now),
            )
            conn.execute(
                "INSERT INTO api_keys (key, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (key, uid, now, self._api_key_expires_at()),
            )
        return {
            "id": uid,
            "email": email,
            "name": name.strip(),
            "role": role,
            "created_at": now,
            "api_key": key,
        }

    def update_user(
        self,
        user_id: str,
        *,
        name: Optional[str] = None,
        role: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return None

            current = dict(row)
            new_role = role if role is not None else current["role"]
            if new_role not in ROLES:
                raise ValueError(f"Unknown role '{new_role}'. Allowed: {ROLES}")

            if current["role"] == "admin" and new_role != "admin":
                admin_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
                ).fetchone()["c"]
                if admin_count <= 1:
                    raise ValueError("Cannot demote the last admin")

            new_email = email.strip().lower() if email else current["email"]
            if new_email != current["email"]:
                dup = conn.execute(
                    "SELECT 1 FROM users WHERE email=? AND id!=?", (new_email, user_id)
                ).fetchone()
                if dup:
                    raise ValueError(f"Email already registered: {new_email}")

            conn.execute(
                "UPDATE users SET email=?, name=?, role=? WHERE id=?",
                (
                    new_email,
                    name.strip() if name is not None else current["name"],
                    new_role,
                    user_id,
                ),
            )
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return False
            if row["role"] == "admin":
                admin_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
                ).fetchone()["c"]
                if admin_count <= 1:
                    raise ValueError("Cannot delete the last admin")
            conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        return True

    def rotate_api_key(self, user_id: str) -> Optional[str]:
        key = self._generate_api_key()
        now = self._now()
        with self._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                return None
            conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
            conn.execute(
                "INSERT INTO api_keys (key, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (key, user_id, now, self._api_key_expires_at()),
            )
        return key

    def set_api_key(self, user_id: str, api_key: str) -> None:
        key = api_key.strip()
        if len(key) < 16:
            raise ValueError("API key must be at least 16 characters")
        now = self._now()
        with self._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                raise ValueError("User not found")
            conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
            conn.execute(
                "INSERT INTO api_keys (key, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (key, user_id, now, self._api_key_expires_at()),
            )

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, name, role, created_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_users(self) -> List[Dict[str, Any]]:
        return self.list_users_detailed()

    def list_users_detailed(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT u.id, u.email, u.name, u.role, u.created_at,
                          k.key, k.created_at AS key_created_at
                   FROM users u
                   LEFT JOIN api_keys k ON k.user_id = u.id
                   ORDER BY u.email"""
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                key = d.pop("key", None)
                d["key_hint"] = f"...{key[-4:]}" if key and len(key) >= 4 else None
                result.append(d)
            return result

    def list_roles(self) -> List[Dict[str, Any]]:
        return [
            {"role": role, "permissions": perms}
            for role, perms in ROLE_PERMISSIONS.items()
        ]

    def auth_status(self) -> Dict[str, Any]:
        from services.auth_bootstrap import env_admin_spec

        spec = env_admin_spec()
        count = self.count_users()
        return {
            "setup_required": count == 0,
            "admin_from_env": spec is not None,
            "env_admin_email": spec["email"] if spec else None,
            "users_count": count,
            "roles": ROLES,
        }

    @staticmethod
    def _generate_api_key() -> str:
        return secrets.token_urlsafe(32)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, name, role FROM users WHERE email=?",
                (email.strip().lower(),),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        now = self._now()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """SELECT u.id, u.email, u.name, u.role, k.expires_at
                   FROM users u JOIN api_keys k ON k.user_id = u.id WHERE k.key=?""",
                (api_key,),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] and row["expires_at"] < now:
                return None
            conn.execute(
                "UPDATE api_keys SET last_used_at=? WHERE key=?",
                (now, api_key),
            )
            return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}

    def has_permission(self, role: str, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(role, [])
        return "*" in perms or permission in perms
