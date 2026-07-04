"""Литобзор: непустой текст при непроверенных фактах."""

from services.synthesis_llm import build_structured_narrative


def test_structured_narrative_uses_unverified_facts():
    sections = {
        "sources_count": 5,
        "verified_sources": 0,
        "key_findings": [
            {
                "subject": "электроэкстракция меди",
                "relation": "uses_material",
                "object": "серная кислота",
                "source_document": "report.pdf",
            },
        ],
        "document_excerpts": [
            {"document": "report.pdf", "text": "Процесс проводят при температуре 60 °C."},
        ],
        "entities": [{"name": "медный катод"}],
        "by_geography": {"RU": 2},
        "disagreements": [],
    }
    text = build_structured_narrative("медь", sections)
    assert "электроэкстракция меди" in text
    assert "report.pdf" in text
    assert len(text) > 200
    assert "#" not in text
