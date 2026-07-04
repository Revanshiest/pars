"""Извлечение ключевых слов из естественно-языковых запросов."""

from __future__ import annotations

import re
from typing import List

# Стоп-слова RU/EN (вопросы, предлоги, местоимения)
_STOP = frozenset({
    "как", "какая", "какой", "какие", "какое", "что", "где", "когда", "кто", "чем", "каков",
    "это", "этот", "эта", "эти", "тот", "та", "те", "ли", "не", "же", "бы", "или", "и", "а",
    "на", "в", "во", "из", "за", "по", "при", "для", "от", "до", "об", "о", "с", "со", "к", "ко",
    "the", "a", "an", "what", "how", "where", "when", "who", "which", "is", "are", "was", "were",
    "at", "on", "in", "for", "of", "to", "from", "with", "by", "per", "year", "annual",
    "годовая", "годовой", "годовое", "сколько", "является", "быть", "есть",
})

_PHRASE_RE = re.compile(r"[A-ZА-ЯЁ][a-zа-яё]+(?:\s+[A-ZА-ЯЁ][a-zа-яё]+)+")
_WORD_RE = re.compile(r"[\w\u0400-\u04ff]+", re.UNICODE)


def extract_search_terms(query: str, extra_text: str = "", *, max_terms: int = 12) -> List[str]:
    """Ключевые слова и фразы для OR-поиска по фактам."""
    if not query or not query.strip():
        return []

    terms: List[str] = []

    for m in _PHRASE_RE.finditer(query):
        phrase = m.group(0).strip().lower()
        if len(phrase) >= 3:
            terms.append(phrase)

    combined = f"{query} {extra_text}".lower()
    for word in _WORD_RE.findall(combined):
        wl = word.lower()
        if len(wl) < 3 or wl in _STOP:
            continue
        if wl not in terms:
            terms.append(wl)

    return terms[:max_terms]
