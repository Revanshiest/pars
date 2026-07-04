"""Экспорт результатов: Markdown, JSON-LD, PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from services.analytics import generate_literature_review
from services.pdf_report import build_pdf_report
from services.rdf_export import triples_to_graph
from services.store import get_store


def export_markdown(topic: str, review: Optional[Dict] = None) -> str:
    review = review or generate_literature_review(topic)
    lines = [
        f"# Литературный обзор: {topic}\n",
        f"**Уверенность:** {review['confidence']:.0%}  ",
        f"**Источников:** {review['sources_count']}  ",
        f"**Верифицировано:** {review['verified_sources']}  ",
        f"**Синтез:** {review.get('synthesis_mode', 'structured')}\n",
        "## Резюме\n",
        (review.get("summary") or "Нет данных для резюме по теме.") + "\n",
    ]

    if review.get("year_summary"):
        lines.append("## Динамика по годам\n")
        lines.append("| Год | Записей | Фактов |\n|-----|---------|--------|\n")
        for year, info in sorted(review["year_summary"].items(), key=lambda x: str(x[0]), reverse=True):
            if str(year) == "unknown":
                continue
            lines.append(f"| {year} | {info.get('count', 0)} | {info.get('facts', 0)} |\n")
        lines.append("\n")

    if review.get("by_geography"):
        lines.append("## Распределение по географии\n")
        for geo, cnt in review["by_geography"].items():
            lines.append(f"- {geo}: {cnt} фактов\n")

    if review.get("by_source_type"):
        lines.append("\n## Типы источников\n")
        for key, info in review["by_source_type"].items():
            lines.append(
                f"- **{info.get('label', key)}**: {info.get('count', 0)} "
                f"(вериф.: {info.get('verified_count', 0)})\n"
            )

    if review.get("consensus_findings"):
        lines.append("\n## Консенсусные выводы\n")
        lines.append("| Субъект | Связь | Объект | Источник | Год |\n")
        lines.append("|---------|-------|--------|----------|-----|\n")
        for f in review["consensus_findings"][:12]:
            prov = f.get("provenance") or {}
            yr = prov.get("year") or (f.get("properties") or {}).get("year", "")
            src = prov.get("source_document") or f.get("source_document", "")
            lines.append(f"| {f['subject']} | {f['relation']} | {f['object']} | {src} | {yr} |\n")

    if review.get("disagreements"):
        lines.append("\n## Зоны разногласий\n")
        for f in review["disagreements"][:5]:
            lines.append(f"- {f['subject']} contradicts {f['object']}\n")

    if review.get("document_excerpts"):
        lines.append("\n## Фрагменты документов\n")
        for i, c in enumerate(review["document_excerpts"][:5], 1):
            text = (c.get("text") or "")[:300]
            lines.append(f"{i}. [{c.get('document', '—')}] {text}...\n")

    return "".join(lines)


def export_jsonld(topic: str, limit: int = 50) -> str:
    store = get_store()
    facts = store.list_facts(limit=limit)
    triples = [
        {
            "subject": f["subject"],
            "subject_type": f["subject_type"],
            "relation": f["relation"],
            "object": f["object"],
            "object_type": f["object_type"],
            "properties": f.get("properties") or {},
            "confidence": f.get("confidence"),
            "geography": f.get("geography"),
        }
        for f in facts
        if topic.lower() in f["subject"].lower() or topic.lower() in f["object"].lower()
    ]
    if not triples:
        triples = [
            {
                "subject": f["subject"], "subject_type": f["subject_type"],
                "relation": f["relation"], "object": f["object"],
                "object_type": f["object_type"],
                "properties": f.get("properties") or {},
            }
            for f in facts[:limit]
        ]
    g = triples_to_graph(triples, source_document=topic)
    return g.serialize(format="json-ld")


def export_pdf(topic: str, review: Optional[Dict] = None) -> bytes:
    review = review or generate_literature_review(topic)
    return build_pdf_report(topic, review)


def save_export(topic: str, fmt: str, output_dir: str = "data/exports") -> Path:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in topic)[:50]
    if fmt == "md":
        path = Path(output_dir) / f"{safe}.md"
        path.write_text(export_markdown(topic), encoding="utf-8")
    elif fmt == "jsonld":
        path = Path(output_dir) / f"{safe}.jsonld"
        path.write_text(export_jsonld(topic), encoding="utf-8")
    elif fmt == "pdf":
        path = Path(output_dir) / f"{safe}.pdf"
        path.write_bytes(export_pdf(topic))
    else:
        raise ValueError(f"Unknown format: {fmt}")
    return path
