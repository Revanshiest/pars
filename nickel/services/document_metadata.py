"""Извлечение библиографических метаданных: год, автор, страница, тип документа."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


YEAR_PATTERN = re.compile(r"\b(19[89]\d|20[0-3]\d)\b")
PAGE_PATTERNS = [
    re.compile(r"(?i)(?:page|стр\.?|с\.)\s*[:\.]?\s*(\d{1,4})"),
    re.compile(r"(?i)\[page\s*(\d{1,4})\]"),
    re.compile(r"(?i)<!--?\s*page\s*(\d{1,4})"),
]
AUTHOR_PATTERNS = [
    re.compile(r"(?i)(?:author[s]?|автор(?:ы)?)\s*[:\-—]\s*(.+?)(?:\n|;|$)"),
    re.compile(r"(?i)(?:by|©)\s+([A-ZА-Я][\w\s\.\-]{2,60})(?:\n|,|\d{4})"),
]


def extract_year(text: str, fallback: Optional[int] = None) -> Optional[int]:
    if not text:
        return fallback
    years = [int(y) for y in YEAR_PATTERN.findall(text[:8000])]
    if not years:
        return fallback
    return max(years)


def extract_page(text: str) -> Optional[int]:
    if not text:
        return None
    sample = text[:1500]
    for pattern in PAGE_PATTERNS:
        m = pattern.search(sample)
        if m:
            page = int(m.group(1))
            if 1 <= page <= 9999:
                return page
    return None


def page_from_chunk(chunk: Dict[str, Any]) -> Optional[int]:
    if chunk.get("page") is not None:
        try:
            return int(chunk["page"])
        except (TypeError, ValueError):
            pass
    return extract_page(chunk.get("text") or "")


def extract_author(text: str) -> Optional[str]:
    if not text:
        return None
    sample = text[:6000]
    for pattern in AUTHOR_PATTERNS:
        m = pattern.search(sample)
        if m:
            author = m.group(1).strip().strip(".")
            if 3 <= len(author) <= 120:
                return author
    return None


def enrich_document_metadata(
    metadata: Dict[str, Any],
    text: str,
    doc_kind: Dict[str, Any],
    geography: Optional[str] = None,
) -> Dict[str, Any]:
    """Дополняет document_metadata полями year, author, document_kind."""
    fair = metadata.get("fair") or {}
    year = metadata.get("year") or extract_year(text)
    if not year and fair.get("updated_at"):
        year = extract_year(str(fair["updated_at"]))

    metadata.setdefault("document_kind", doc_kind.get("kind", "report"))
    metadata.setdefault("document_label", doc_kind.get("label"))
    metadata.setdefault("year", year)
    metadata.setdefault("author", extract_author(text))
    if geography:
        metadata.setdefault("geography", geography)
    return metadata
