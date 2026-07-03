"""Unit-тесты экспорта."""

from __future__ import annotations

from services.export_service import export_markdown
from services.pdf_report import build_pdf_report


SAMPLE_REVIEW = {
    "confidence": 0.7,
    "sources_count": 3,
    "verified_sources": 1,
    "synthesis_mode": "structured",
    "llm_synthesized": False,
    "summary": "Тестовое резюме на русском.",
    "year_summary": {"2024": {"count": 2, "facts": 5}},
    "by_geography": {"Россия": 2},
    "by_source_type": {
        "publication": {"label": "Публикации", "count": 2, "verified_count": 1}
    },
    "consensus_findings": [],
    "disagreements": [],
    "document_excerpts": [],
}


def test_export_markdown_russian():
    md = export_markdown("никель", review=SAMPLE_REVIEW)
    assert "Литературный обзор" in md
    assert "70%" in md or "0.7" in md.lower() or "70" in md


def test_pdf_cyrillic_bytes():
    pdf = build_pdf_report("Никель", SAMPLE_REVIEW)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000
