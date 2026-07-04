"""Безопасная загрузка файлов."""

from __future__ import annotations

import os
import re
from pathlib import Path

ALLOWED_SUFFIXES = {".pdf", ".md", ".txt", ".docx", ".xlsx", ".xls", ".json"}
_UNSAFE = re.compile(r"[^\w.\- ()]+", re.UNICODE)


def sanitize_filename(name: str) -> str:
    base = Path(name or "document").name
    if ".." in base or base.startswith("."):
        base = "document"
    base = _UNSAFE.sub("_", base).strip("._")
    return base or "document"


def max_upload_bytes() -> int:
    mb = int(os.getenv("MAX_UPLOAD_MB", "100"))
    return mb * 1024 * 1024
