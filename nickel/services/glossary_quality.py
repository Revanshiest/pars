"""Фильтрация и очистка терминов глоссария (шум из пайплайна)."""

from __future__ import annotations

import re

_JOB_PREFIX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_\d+\s*",
    re.I,
)
_ARTIFACT_SUFFIX = re.compile(r"_(yandex_graph|extracted|ttl)$", re.I)


def clean_glossary_display(name: str) -> str:
    """Убирает префикс job_id и служебные суффиксы для отображения."""
    s = (name or "").strip()
    s = _JOB_PREFIX.sub("", s)
    s = _ARTIFACT_SUFFIX.sub("", s)
    return s.strip() or name.strip()


def is_worthy_glossary_term(name: str) -> bool:
    """Отсекает служебные строки, попавшие в глоссарий из пайплайна."""
    s = (name or "").strip()
    if len(s) < 2 or len(s) > 120:
        return False
    if _JOB_PREFIX.match(s):
        return False
    low = s.lower()
    if "_yandex_graph" in low or "_extracted.json" in low:
        return False
    if s.count("_") >= 4 and re.search(r"[0-9a-f-]{36}", s, re.I):
        return False
    return True


def term_language(name: str) -> str:
    return "ru" if re.search(r"[а-яё]", name or "", re.I) else "en"
