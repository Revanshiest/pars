"""Определение языка запроса и кросс-языковое расширение."""

from __future__ import annotations

import re
from typing import Dict, List


def detect_query_language(text: str) -> str:
    """ru | en | mixed"""
    cyr = len(re.findall(r"[а-яёА-ЯЁ]", text))
    lat = len(re.findall(r"[a-zA-Z]", text))
    if cyr > 0 and lat > 0:
        return "mixed"
    if cyr > lat:
        return "ru"
    if lat > 0:
        return "en"
    return "ru"


def bilingual_search_queries(query: str) -> Dict[str, str]:
    """Формирует RU/EN варианты запроса для BGE cross-lingual search."""
    lang = detect_query_language(query)
    return {
        "original": query,
        "detected_language": lang,
        "ru": query if lang in ("ru", "mixed") else query,
        "en": query if lang in ("en", "mixed") else query,
    }


def merge_search_results(*result_lists: List[dict], key_fn=None, limit: int = 10) -> List[dict]:
    """Дедупликация результатов из RU/EN поиска."""
    seen = set()
    merged = []
    for results in result_lists:
        for item in results:
            if key_fn:
                k = key_fn(item)
            elif "text" in item:
                k = item["text"][:100]
            elif "name" in item:
                k = item["name"]
            elif "id" in item:
                k = item["id"]
            else:
                k = str(item)
            if k not in seen:
                seen.add(k)
                merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged
