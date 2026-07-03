"""JWT-токены для API (обмен API-key → Bearer)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    import jwt
except ImportError:
    jwt = None  # type: ignore

JWT_ALGORITHM = "HS256"


def _secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret or len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be set (min 32 chars) to use token auth")
    return secret


def token_ttl_hours() -> int:
    return int(os.getenv("JWT_EXPIRE_HOURS", "24"))


def create_access_token(user: Dict[str, Any]) -> Dict[str, Any]:
    if jwt is None:
        raise RuntimeError("PyJWT not installed")
    now = datetime.now(timezone.utc)
    exp = now + timedelta(hours=token_ttl_hours())
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "role": user["role"],
        "name": user.get("name"),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    token = jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": token_ttl_hours() * 3600,
        "expires_at": exp.isoformat(),
    }


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    if jwt is None:
        return None
    secret = os.getenv("JWT_SECRET", "")
    if not secret or len(secret) < 32:
        return None
    try:
        payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return {
            "id": payload["sub"],
            "email": payload.get("email"),
            "role": payload.get("role"),
            "name": payload.get("name"),
        }
    except Exception:
        return None
