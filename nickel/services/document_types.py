"""Классификация типа документа: патент, норматив, публикация, отчёт, каталог."""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


PATENT_MARKERS = [
    "patent", "патент", "wo20", "us20", "ep20", "ru20", "заявка", "изобретен",
]
REGULATION_MARKERS = [
    "gost", "гost", "гост", "snip", "снип", "norm", "норматив", "regulation",
    "sanpin", "санпин", "приказ", "standard", "стандарт",
]
PUBLICATION_MARKERS = [
    "article", "journal", "doi", "abstract", "publication", "статья", "журнал",
]
EXPERIMENT_CATALOG_MARKERS = [
    "experiment", "эксперимент", "catalog", "каталог", "protocol", "протокол",
    "опыт", "реестр",
]


def detect_document_kind(filepath: str, text_sample: str = "") -> Dict[str, Any]:
    name = os.path.basename(filepath).lower()
    sample = (text_sample or "")[:3000].lower()
    combined = name + " " + sample

    if any(m in combined for m in PATENT_MARKERS):
        return {"kind": "patent", "ontology_type": "Publication", "label": "Патент"}
    if any(m in combined for m in REGULATION_MARKERS):
        return {"kind": "regulation", "ontology_type": "Regulation", "label": "Нормативный документ"}
    if any(m in combined for m in EXPERIMENT_CATALOG_MARKERS):
        return {"kind": "experiment_catalog", "ontology_type": "Experiment", "label": "Каталог экспериментов"}
    if any(m in combined for m in PUBLICATION_MARKERS):
        return {"kind": "publication", "ontology_type": "Publication", "label": "Публикация"}
    if name.endswith((".xlsx", ".xls")):
        return {"kind": "experiment_catalog", "ontology_type": "Experiment", "label": "Табличный каталог"}
    return {"kind": "report", "ontology_type": "Document", "label": "Технический документ"}


def enrich_triples_with_document_context(
    triples: List[Dict[str, Any]],
    filepath: str,
    text_sample: str = "",
) -> List[Dict[str, Any]]:
    """Добавляет метаданные документа и связь described_in для патентов/нормативов."""
    doc_info = detect_document_kind(filepath, text_sample)
    basename = os.path.basename(filepath)
    doc_name = os.path.splitext(basename)[0]

    for t in triples:
        props = t.setdefault("properties", {})
        props.setdefault("source_file", basename)
        props.setdefault("document_kind", doc_info["kind"])
        if doc_info["kind"] in ("patent", "regulation", "publication"):
            props.setdefault("document_class", doc_info["label"])

    anchor = {
        "subject": doc_name,
        "subject_type": doc_info["ontology_type"],
        "relation": "described_in",
        "object": basename,
        "object_type": "Document",
        "properties": {
            "document_kind": doc_info["kind"],
            "label": doc_info["label"],
        },
    }
    return [anchor] + triples
