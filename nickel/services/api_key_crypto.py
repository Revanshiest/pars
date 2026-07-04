"""Хеширование API-ключей (SHA-256 lookup, без хранения plaintext)."""

from __future__ import annotations

import hashlib
import re


_HEX64 = re.compile(r"^[a-f0-9]{64}$")


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.strip().encode("utf-8")).hexdigest()


def key_hint(api_key: str) -> str:
    k = api_key.strip()
    return f"...{k[-4:]}" if len(k) >= 4 else "****"


def is_hashed_stored(stored: str) -> bool:
    return bool(stored and _HEX64.match(stored))


def keys_match(stored: str, provided: str) -> bool:
    if is_hashed_stored(stored):
        return stored == hash_api_key(provided)
    return stored == provided.strip()


def storage_value(api_key: str) -> str:
    """Значение для колонки api_keys.key — только хеш."""
    return hash_api_key(api_key)
