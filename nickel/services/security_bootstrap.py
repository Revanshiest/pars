"""Проверка обязательных секретов при старте."""

from __future__ import annotations

import os
import re
import secrets
import sys

from services.logging_config import get_logger

logger = get_logger(__name__)

_PLACEHOLDER_JWT = {
    "change-me-to-random-32-char-secret-key-minimum",
    "change-me-to-random-32-char-secret-key!!",
}
_PLACEHOLDER_NEO4J = {"nickel_kg_pass", "password", "neo4j"}


def _is_production() -> bool:
    return os.getenv("ENV", "development").lower() in ("production", "prod")


def validate_secrets() -> None:
    jwt = (os.getenv("JWT_SECRET") or "").strip()
    if len(jwt) < 32:
        if _is_production():
            msg = "JWT_SECRET must be at least 32 characters"
            logger.error(msg)
            raise RuntimeError(msg)
        jwt = secrets.token_urlsafe(32)
        os.environ["JWT_SECRET"] = jwt
        logger.warning("JWT_SECRET was missing — generated ephemeral dev secret (set in .env to persist)")
    elif jwt.lower() in _PLACEHOLDER_JWT:
        if _is_production():
            msg = "JWT_SECRET is a placeholder — generate a random secret"
            logger.error(msg)
            raise RuntimeError(msg)
        logger.warning("JWT_SECRET is a placeholder — acceptable only in development")

    if _is_production():
        neo4j_pass = (os.getenv("NEO4J_PASSWORD") or "").strip()
        if not neo4j_pass or neo4j_pass in _PLACEHOLDER_NEO4J:
            msg = "NEO4J_PASSWORD must be set to a strong value in production"
            logger.error(msg)
            raise RuntimeError(msg)
        if os.getenv("ALLOW_AUTH_SETUP", "false").lower() in ("1", "true", "yes"):
            msg = "ALLOW_AUTH_SETUP must be false in production"
            logger.error(msg)
            raise RuntimeError(msg)


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if _is_production():
        return []
    return ["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"]


def docs_enabled() -> bool:
    if os.getenv("ENABLE_API_DOCS", "").lower() in ("0", "false", "no"):
        return False
    return not _is_production() or os.getenv("ENABLE_API_DOCS", "").lower() in ("1", "true", "yes")
