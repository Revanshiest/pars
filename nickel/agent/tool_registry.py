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


def select_tools(question: str) -> List[Dict[str, Any]]:
    """Автовыбор инструментов по вопросу (без LLM). Всегда search_facts + glossary."""
    q = question.lower()
    plan: List[Dict[str, Any]] = [
        {"name": "search_facts", "arguments": {"query": question, "limit": 15}},
        {"name": "glossary_lookup", "arguments": {"text": question}},
    ]

    if any(w in q for w in [
        "отечествен", "зарубеж", "миров", "ru vs", "сравни", "vs мир", "domestic",
    ]):
        plan.append({"name": "compare_practices", "arguments": {"query": question}})

    if any(w in q for w in ["мг/л", "концентрац", "≤", "≥", "<", ">", "%", "ppm"]):
        plan.append({"name": "numeric_search", "arguments": {"query": question}})

    if any(w in q for w in ["связ", "граф", "relationship", "сосед", "цепоч"]):
        entities = re.findall(
            r"[A-ZА-ЯЁ][a-zа-яё0-9\-]+(?:\s+[A-ZА-ЯЁ][a-zа-яё0-9\-]+)?",
            question,
        )
        if entities:
            plan.append({
                "name": "explore_graph",
                "arguments": {"entity_name": entities[0], "limit": 20},
            })

    if any(w in q for w in ["сколько факт", "статистик", "объём баз", "сколько документ"]):
        plan.append({"name": "knowledge_stats", "arguments": {}})

    # Именованная сущность для обхода графа — через токены запроса
    if not any(p["name"] == "explore_graph" for p in plan):
        from services.query_tokens import extract_search_terms
        terms = extract_search_terms(question)
        for term in terms:
            if term[0].isupper() or len(term) >= 4:
                plan.append({
                    "name": "explore_graph",
                    "arguments": {"entity_name": term, "limit": 15},
                })
                break

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
    return out[:5]
