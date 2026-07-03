"""FAIR-метаданные: DOI, дата актуализации, provenance."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


DOI_PATTERN = re.compile(
    r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)


def extract_doi(text: str) -> Optional[str]:
    m = DOI_PATTERN.search(text or "")
    return m.group(1).lower() if m else None


def build_fair_metadata(
    source_document: str,
    job_id: str,
    document_kind: str = "report",
    doi: Optional[str] = None,
    source_file_path: Optional[str] = None,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "findable": {
            "identifier": doi or f"doc:{source_document}",
            "source_document": source_document,
            "job_id": job_id,
        },
        "accessible": {
            "access_level": "internal",
            "source_file": source_file_path or source_document,
        },
        "interoperable": {
            "ontology": "nickel-kg-v1",
            "format": "application/ld+json",
            "document_kind": document_kind,
        },
        "reusable": {
            "license": "internal-rd-use",
            "provenance": "llm_extraction_pipeline",
        },
        "doi": doi,
        "updated_at": now,
        "valid_from": now,
    }


def attach_provenance(
    triples: List[Dict[str, Any]],
    *,
    source_document: str,
    job_id: str,
    fair: Dict[str, Any],
    chunks: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    chunk_map = {c["id"]: c for c in (chunks or [])}
    for t in triples:
        props = t.setdefault("properties", {})
        chunk_id = t.get("source_chunk")
        props["source_document"] = source_document
        props["job_id"] = job_id
        props["doi"] = fair.get("doi")
        props["updated_at"] = fair.get("updated_at")
        props["valid_from"] = fair.get("valid_from")
        props["fair"] = {
            k: v for k, v in fair.items()
            if k not in ("doi", "updated_at", "valid_from")
        }
        if chunk_id and chunk_id in chunk_map:
            props["source_chunk"] = chunk_id
            props["source_headers"] = chunk_map[chunk_id].get("headers", "")
            props["source_excerpt"] = (chunk_map[chunk_id].get("text") or "")[:300]
            page = chunk_map[chunk_id].get("page")
            if page is not None:
                props["source_page"] = page
            t["source_chunk"] = chunk_id
            if page is not None:
                t["source_page"] = page
        elif chunk_id:
            props["source_chunk"] = chunk_id
            t["source_chunk"] = chunk_id
    return triples
