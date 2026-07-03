"""Bootstrap admin из AUTH_ADMIN в .env."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from services.store import get_store


def env_admin_spec() -> Optional[Dict[str, str]]:
    """AUTH_ADMIN=email|name|api_key (api_key мин. 16 символов)."""
    raw = os.getenv("AUTH_ADMIN", "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        raise ValueError("AUTH_ADMIN must be: email|name|api_key (min 16 chars for key)")
    email, name, api_key = parts[0], parts[1], parts[2]
    if "@" not in email:
        raise ValueError("AUTH_ADMIN: invalid email")
    if len(api_key) < 16:
        raise ValueError("AUTH_ADMIN: api_key must be at least 16 characters")
    return {"email": email.lower(), "name": name, "api_key": api_key}


def is_env_admin_email(email: str) -> bool:
    spec = env_admin_spec()
    return bool(spec and spec["email"] == email.strip().lower())


def bootstrap_admin_from_env() -> bool:
    """Создать/синхронизировать admin из AUTH_ADMIN. Возвращает True если admin готов."""
    spec = env_admin_spec()
    if not spec:
        return get_store().count_admins() > 0

    store = get_store()
    existing = store.get_user_by_email(spec["email"])
    if existing:
        if existing["role"] != "admin":
            store.update_user(existing["id"], role="admin")
        store.set_api_key(existing["id"], spec["api_key"])
        return True

    store.create_user(
        spec["email"],
        spec["name"],
        "admin",
        api_key=spec["api_key"],
    )
    return True


def assignable_roles() -> list[str]:
    from services.store import ROLES

    if env_admin_spec():
        return [r for r in ROLES if r != "admin"]
    return list(ROLES)
