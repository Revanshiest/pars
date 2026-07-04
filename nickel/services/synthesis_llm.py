"""LLM-синтез литобзора (YandexGPT / Ollama) с развёрнутым текстовым fallback."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from services.logging_config import get_logger

logger = get_logger(__name__)

LIT_REVIEW_SYSTEM = (
    "Ты — аналитик R&D Knowledge Graph в горно-металлургии. "
    "Пиши связный обзор на русском языке обычными абзацами, без markdown-заголовков и списков с #."
)

LIT_REVIEW_PROMPT = """Подготовь литературный обзор по теме: {topic}

Требования:
- 6–10 предложений минимум, разбей на 3–4 абзаца.
- Первый абзац — общая картина по теме и охват источников.
- Далее — ключевые технологии, параметры, материалы и практики из контекста.
- Укажи, если факты не проходили экспертную проверку.
- Опирайся ТОЛЬКО на контекст ниже. Не выдумывай.

Контекст:
{context}
"""


def _build_context_payload(sections: Dict[str, Any]) -> str:
    findings = sections.get("key_findings") or sections.get("consensus_findings") or []
    payload = {
        "sources_count": sections.get("sources_count"),
        "verified_sources": sections.get("verified_sources"),
        "findings": [
            {
                "subject": x.get("subject"),
                "relation": x.get("relation"),
                "object": x.get("object"),
                "source": x.get("source_document") or (x.get("provenance") or {}).get("source_document"),
                "verified": x.get("verification_status") == "verified",
            }
            for x in findings[:15]
        ],
        "disagreements": [
            {"subject": x.get("subject"), "object": x.get("object")}
            for x in sections.get("disagreements", [])[:5]
        ],
        "excerpts": [
            {"document": c.get("document"), "text": (c.get("text") or "")[:400]}
            for c in sections.get("document_excerpts", [])[:6]
        ],
        "entities": [e.get("name") for e in sections.get("entities", [])[:10]],
        "by_geography": sections.get("by_geography", {}),
        "by_source_type": sections.get("by_source_type", {}),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _fact_source(f: Dict[str, Any]) -> str:
    prov = f.get("provenance") or {}
    return prov.get("source_document") or f.get("source_document") or "документ не указан"


def _relation_label(rel: str) -> str:
    labels = {
        "uses_material": "использует материал",
        "operates_at_condition": "работает при условии",
        "produces_output": "даёт продукт",
        "has_property": "имеет свойство",
        "located_in": "расположено в",
        "related_to": "связано с",
        "part_of": "является частью",
    }
    return labels.get(rel, "связано с")


def build_structured_narrative(topic: str, sections: Dict[str, Any]) -> str:
    """Развёрнутый обзор без markdown — для случаев без LLM или как fallback."""
    n_sources = int(sections.get("sources_count") or 0)
    n_verified = int(sections.get("verified_sources") or 0)
    findings: List[Dict] = sections.get("key_findings") or sections.get("consensus_findings") or []
    excerpts = sections.get("document_excerpts") or []
    entities = sections.get("entities") or []
    disagreements = sections.get("disagreements") or []
    by_geo = sections.get("by_geography") or {}

    parts: List[str] = []

    intro = (
        f"По теме «{topic}» в базе знаний найдено {n_sources} связанных записей "
        f"из загруженных документов."
    )
    if n_verified == 0:
        intro += (
            " Пока ни один из связанных фактов не прошёл экспертную проверку — "
            "ниже приведены автоматически извлечённые данные, их стоит подтвердить в разделе верификации."
        )
    else:
        intro += f" {n_verified} записей уже проверены экспертами."
    parts.append(intro)

    if findings:
        lines = []
        for f in findings[:8]:
            subj = f.get("subject") or "—"
            obj = f.get("object") or "—"
            rel = _relation_label(f.get("relation") or "")
            src = _fact_source(f)
            lines.append(f"{subj} {rel} {obj} (источник: {src}).")
        parts.append("Ключевые положения из документов: " + " ".join(lines))

    if excerpts:
        quote_parts = []
        for c in excerpts[:4]:
            text = (c.get("text") or "").strip()
            if not text:
                continue
            doc = c.get("document") or "документ"
            snippet = text[:280] + ("…" if len(text) > 280 else "")
            quote_parts.append(f"В «{doc}» упоминается: «{snippet}»")
        if quote_parts:
            parts.append(" ".join(quote_parts))

    entity_names = [e.get("name") for e in entities[:8] if e.get("name")]
    if entity_names:
        parts.append(f"Чаще всего в материалах фигурируют: {', '.join(entity_names)}.")

    geo_known = {k: v for k, v in by_geo.items() if k and str(k) != "unknown" and v}
    if geo_known:
        geo_text = ", ".join(f"{g} ({c} упом.)" for g, c in sorted(geo_known.items(), key=lambda x: -x[1]))
        parts.append(f"География упоминаний: {geo_text}.")

    if disagreements:
        d_lines = [
            f"{f.get('subject')} и {f.get('object')} описаны по-разному в разных источниках"
            for f in disagreements[:3]
        ]
        parts.append("Есть расхождения между источниками: " + "; ".join(d_lines) + ".")

    if not findings and not excerpts:
        parts.append(
            "По этой формулировке темы автоматический поиск нашёл мало структурированных фактов. "
            "Попробуйте уточнить запрос или загрузить дополнительные отчёты по меди и электроэкстракции."
        )

    return "\n\n".join(parts)


def _try_yandex_synthesis(topic: str, sections: Dict[str, Any]) -> Optional[str]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from services.yandex_llm import get_yandex_chat

        llm = get_yandex_chat(temperature=0.35)
        context = _build_context_payload(sections)
        messages = [
            SystemMessage(content=LIT_REVIEW_SYSTEM),
            HumanMessage(content=LIT_REVIEW_PROMPT.format(topic=topic, context=context)),
        ]
        response = llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        if isinstance(text, list):
            text = "".join(
                block.get("text", str(block)) if isinstance(block, dict) else str(block)
                for block in text
            )
        text = str(text or "").strip()
        if len(text) >= 120:
            return text
    except Exception as exc:
        logger.warning("YandexGPT lit review failed: %s", exc)
    return None


def _try_ollama_synthesis(topic: str, sections: Dict[str, Any]) -> Optional[str]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_ollama import ChatOllama

        llm = ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0.25,
        )
        context = _build_context_payload(sections)
        messages = [
            SystemMessage(content=LIT_REVIEW_SYSTEM),
            HumanMessage(content=LIT_REVIEW_PROMPT.format(topic=topic, context=context)),
        ]
        response = llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        text = str(text or "").strip()
        if len(text) >= 120:
            return text
    except Exception as exc:
        logger.warning("Ollama lit review failed: %s", exc)
    return None


def synthesize_literature_review(
    topic: str,
    sections: Dict[str, Any],
    force_llm: Optional[bool] = None,
) -> tuple[str, bool]:
    """Возвращает (summary, llm_used)."""
    use_llm = force_llm if force_llm is not None else (
        os.getenv("LIT_REVIEW_USE_LLM", "true").lower() == "true"
    )

    if use_llm:
        backend = os.getenv("LIT_REVIEW_LLM", "yandex").lower()
        text = None
        if backend == "yandex":
            text = _try_yandex_synthesis(topic, sections)
            if not text:
                text = _try_ollama_synthesis(topic, sections)
        else:
            text = _try_ollama_synthesis(topic, sections)
            if not text:
                text = _try_yandex_synthesis(topic, sections)
        if text:
            return text, True

    return build_structured_narrative(topic, sections), False
