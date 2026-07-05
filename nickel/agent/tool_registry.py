"""Каталог инструментов чат-агента (описания + исполнение)."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


TOOL_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "search_facts",
        "description": "Поиск фактов (subject-relation-object) в базе знаний SQLite по вопросу или ключевым словам.",
        "parameters": {"query": "строка поиска", "limit": "число результатов (1-20)"},
    },
    {
        "name": "compare_practices",
        "description": "Сравнение отечественной (RU) и мировой практики по теме.",
        "parameters": {"query": "тема сравнения"},
    },
    {
        "name": "numeric_search",
        "description": "Поиск фактов с числовыми ограничениями (мг/л, %, ≤, ≥).",
        "parameters": {"query": "числовой запрос"},
    },
    {
        "name": "explore_graph",
        "description": "Связи сущности в графе знаний (соседи, связи has_property, uses_material и т.д.).",
        "parameters": {"entity_name": "имя сущности", "limit": "макс. связей"},
    },
    {
        "name": "glossary_lookup",
        "description": "Поиск терминов и синонимов RU/EN в глоссарии нормализации.",
        "parameters": {"text": "фрагмент текста или термин"},
    },
    {
        "name": "knowledge_stats",
        "description": "Общая статистика базы: число фактов, документов, терминов глоссария.",
        "parameters": {},
    },
]


def catalog_for_prompt() -> str:
    lines = []
    for t in TOOL_CATALOG:
        params = ", ".join(f"{k}: {v}" for k, v in t["parameters"].items()) or "нет"
        lines.append(f"- **{t['name']}**: {t['description']} Параметры: {params}.")
    return "\n".join(lines)


def _strip_auto_hints(q: str) -> str:
    """Убрать хвостовые подсказки из стартовых вопросов — они не означают запрос сравнения."""
    for suffix in (
        "отечественная и мировая практика по загруженным материалам.",
        "по отечественным источникам в базе.",
        "по зарубежным источникам в базе.",
    ):
        q = q.replace(suffix, "")
    return q.strip()


def _wants_compare(q: str) -> bool:
    core = _strip_auto_hints(q)
    if any(w in core for w in ("сравни", " vs ", "ru vs", "vs мир", "domestic vs", "global practice")):
        return True
    return "отечествен" in core and ("миров" in core or "зарубеж" in core)


def select_tools(question: str) -> List[Dict[str, Any]]:
    """Автовыбор инструментов по вопросу (без LLM)."""
    q = question.lower()
    plan: List[Dict[str, Any]] = [
        {"name": "search_facts", "arguments": {"query": question, "limit": 12}},
    ]

    if len(question) <= 140:
        plan.append({"name": "glossary_lookup", "arguments": {"text": question[:200]}})

    if _wants_compare(q):
        plan.append({"name": "compare_practices", "arguments": {"query": question, "limit": 8}})

    if any(w in q for w in ["мг/л", "концентрац", "≤", "≥", "<", ">", "ppm"]) or re.search(
        r"\d+\s*мг", q
    ):
        plan.append({"name": "numeric_search", "arguments": {"query": question}})

    if any(w in q for w in ["связ", "граф", "relationship", "сосед", "цепоч"]):
        entities = re.findall(
            r"[A-ZА-ЯЁ][a-zа-яё0-9\-]+(?:\s+[A-ZА-ЯЁ][a-zа-яё0-9\-]+)?",
            question,
        )
        if entities:
            plan.append({
                "name": "explore_graph",
                "arguments": {"entity_name": entities[0], "limit": 12},
            })

    if any(w in q for w in ["сколько факт", "статистик", "объём баз", "сколько документ"]):
        plan.append({"name": "knowledge_stats", "arguments": {}})

    return _dedupe_plan(plan)


def _dedupe_plan(plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for step in plan:
        key = step["name"]
        if key in seen:
            continue
        seen.add(key)
        out.append(step)
    return out[:4]
