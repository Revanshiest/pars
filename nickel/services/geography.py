"""Определение географии документов и фактов (RU / EN / global)."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from services.platform_config import geography_markers


def _markers() -> Dict[str, Any]:
    return geography_markers()


def detect_geography(
    text: str,
    filepath: str = "",
    doc_kind: Optional[Dict[str, Any]] = None,
) -> str:
    """Определяет geography документа по метаданным, имени файла и содержимому."""
    cfg = _markers()
    ru_markers = cfg.get("ru_markers") or []
    en_markers = cfg.get("en_markers") or []
    ru_journals = cfg.get("ru_journals") or []

    name = os.path.basename(filepath or "").lower()
    header = (text or "")[:12000].lower()
    combined = f"{name} {header}"

    kind = (doc_kind or {}).get("kind") if doc_kind else None
    if kind == "regulation":
        return "RU"
    if kind == "patent":
        if any(m in combined for m in ("ru20", "россий", " rf ", "рф")):
            return "RU"
        if any(m in combined for m in ("us20", "ep20", "wo20", "international")):
            return "EN"

    if any(m in name for m in (".ru.", "_ru_", "-ru-", "gost", "гost")):
        return "RU"

    ru_score = sum(1 for m in ru_markers if m in combined)
    ru_score += sum(2 for m in ru_journals if m in combined)
    en_score = sum(1 for m in en_markers if m in combined)

    cyr = len(re.findall(r"[а-яё]", header[:8000]))
    lat = len(re.findall(r"[a-z]", header[:8000]))
    if cyr > lat * 2 and cyr > 80:
        ru_score += 2
    elif lat > cyr * 2 and lat > 80:
        en_score += 2

    if ru_score > en_score and ru_score >= 1:
        return "RU"
    if en_score > ru_score and en_score >= 1:
        return "EN"
    if ru_score == en_score and ru_score >= 2:
        return "global"
    return "global"


def resolve_fact_geography(
    triple: Dict[str, Any],
    document_geography: Optional[str],
) -> Optional[str]:
    """География факта: явное поле → свойства → документ."""
    if triple.get("geography"):
        return triple["geography"]
    props = triple.get("properties") or {}
    if props.get("geography"):
        return props["geography"]
    return document_geography
