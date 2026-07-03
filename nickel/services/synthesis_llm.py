"""LLM-синтез литобзора (Ollama) с fallback на структурированный текст."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


LIT_REVIEW_PROMPT = """Ты — эксперт по горно-металлургическим R&D. Напиши литературный обзор на русском языке.

Тема: {topic}

Структура ответа (markdown):
## Консенсус
## Разногласия и пробелы
## Динамика по годам (если есть данные)
## Практические выводы

Опирайся ТОЛЬКО на предоставленный контекст. Указывай источники (документ, DOI, год).
Если данных мало — явно укажи пробелы.

Контекст:
{context}
"""


def _build_context_payload(sections: Dict[str, Any]) -> str:
    payload = {
        "by_year": sections.get("by_year", {}),
        "consensus": [
            {
                "triple": f"{x['subject']} —[{x['relation']}]→ {x['object']}",
                "year": (x.get("properties") or {}).get("year"),
                "source": x.get("source_document"),
                "doi": x.get("provenance", {}).get("doi") if x.get("provenance") else x.get("doi"),
            }
            for x in sections.get("consensus_findings", [])[:12]
        ],
        "disagreements": [
            f"{x['subject']} contradicts {x['object']}"
            for x in sections.get("disagreements", [])[:5]
        ],
        "excerpts": [
            {"document": c.get("document"), "text": (c.get("text") or "")[:300]}
            for c in sections.get("document_excerpts", [])[:6]
        ],
        "entities": [e.get("name") for e in sections.get("entities", [])[:10]],
        "by_geography": sections.get("by_geography", {}),
        "by_source_type": sections.get("by_source_type", {}),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_structured_narrative(topic: str, sections: Dict[str, Any]) -> str:
    parts = [f"# Литературный обзор: {topic}\n"]

    by_year = sections.get("by_year") or {}
    if by_year:
        parts.append("## Динамика по годам\n")
        for year, items in sorted(by_year.items(), key=lambda x: str(x[0]), reverse=True):
            if str(year) == "unknown":
                continue
            parts.append(f"- **{year}**: {len(items)} факт(ов)")
            for it in items[:3]:
                parts.append(f"  - {it.get('title', it.get('triple', ''))}")
        parts.append("")

    consensus = sections.get("consensus_findings", [])
    if consensus:
        parts.append("## Консенсус\n")
        for f in consensus[:8]:
            prov = f.get("provenance") or {}
            src = prov.get("source_document") or f.get("source_document") or "—"
            yr = prov.get("year") or (f.get("properties") or {}).get("year") or "?"
            parts.append(
                f"- {f['subject']} —[{f['relation']}]→ {f['object']} "
                f"(источник: {src}, {yr})"
            )
        parts.append("")

    disagreements = sections.get("disagreements", [])
    if disagreements:
        parts.append("## Противоречия\n")
        for f in disagreements[:5]:
            parts.append(f"- {f['subject']} ↔ {f['object']}")
        parts.append("")

    ivp = sections.get("internal_vs_publication") or {}
    if ivp.get("shared_topics"):
        parts.append("## Отечественная vs мировая практика\n")
        parts.append(f"Общие темы: {', '.join(ivp['shared_topics'][:6])}")
        if ivp.get("topics_internal_only"):
            parts.append(f"Только в отчётах: {', '.join(ivp['topics_internal_only'][:4])}")
        if ivp.get("topics_publication_only"):
            parts.append(f"Только в публикациях: {', '.join(ivp['topics_publication_only'][:4])}")
        parts.append("")

    parts.append(f"\n*Охват: {sections.get('sources_count', 0)} источников, "
                 f"уверенность {sections.get('confidence', 0):.0%}*")
    return "\n".join(parts)


def synthesize_literature_review(
    topic: str,
    sections: Dict[str, Any],
    force_llm: Optional[bool] = None,
) -> tuple[str, bool]:
    """Возвращает (summary, llm_used)."""
    use_llm = force_llm if force_llm is not None else (
        os.getenv("LIT_REVIEW_USE_LLM", "true").lower() == "true"
    )
    if not use_llm:
        return build_structured_narrative(topic, sections), False

    try:
        from langchain_ollama import ChatOllama
        from langchain_core.messages import HumanMessage, SystemMessage

        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0.25,
        )
        context = _build_context_payload(sections)
        messages = [
            SystemMessage(content="Ты аналитик R&D Knowledge Graph. Пиши структурированно, по-русски."),
            HumanMessage(content=LIT_REVIEW_PROMPT.format(topic=topic, context=context)),
        ]
        response = llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        if text and len(text.strip()) > 100:
            return text.strip(), True
    except Exception:
        pass

    return build_structured_narrative(topic, sections), False
