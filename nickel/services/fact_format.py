"""Человекочитаемое представление фактов для поиска и UI."""

from __future__ import annotations

from typing import Any, Dict, Optional


def format_fact_answer(fact: Dict[str, Any]) -> str:
    """Краткий ответ по факту: значение + описание."""
    props = fact.get("properties") or {}
    value = _clean(props.get("value"))
    desc = _clean(props.get("description"))
    unit = _clean(props.get("unit"))
    year = _clean(props.get("year"))

    parts: list[str] = []
    if value:
        line = value
        if unit and unit not in value:
            line = f"{value} {unit}"
        parts.append(line)
    if desc and desc not in parts:
        parts.append(desc)
    if year:
        parts.append(f"({year})")

    if parts:
        return " ".join(parts)

    subj = fact.get("subject") or ""
    rel = fact.get("relation") or "related_to"
    obj = fact.get("object") or ""
    return f"{subj} {rel} {obj}".strip()


def format_fact_title(fact: Dict[str, Any]) -> str:
    subj = fact.get("subject") or "?"
    rel = fact.get("relation") or "related_to"
    obj = fact.get("object") or "?"
    return f"{subj} —[{rel}]→ {obj}"


def fact_display_fields(fact: Dict[str, Any]) -> Dict[str, Optional[str]]:
    props = fact.get("properties") or {}
    return {
        "title": format_fact_title(fact),
        "answer": format_fact_answer(fact),
        "value": _clean(props.get("value")),
        "description": _clean(props.get("description")),
        "unit": _clean(props.get("unit")),
        "year": _clean(props.get("year")),
    }


def _clean(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s or None
