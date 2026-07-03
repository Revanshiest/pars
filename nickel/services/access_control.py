"""Document-level ACL: разграничение internal / partner / public."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

ACCESS_LEVELS = ("internal", "partner", "public")

# По умолчанию: внутренние отчёты закрыты, публикации/патенты — для партнёров
DEFAULT_ACCESS_BY_KIND = {
    "publication": "partner",
    "patent": "partner",
    "regulation": "partner",
    "report": "internal",
    "experiment_catalog": "internal",
}

ROLE_ACCESS = {
    "admin": {"internal", "partner", "public"},
    "project_manager": {"internal", "partner", "public"},
    "analyst": {"internal", "partner", "public"},
    "researcher": {"internal", "partner", "public"},
    "external_partner": {"partner", "public"},
}


def default_access_level(document_kind: Optional[str]) -> str:
    return DEFAULT_ACCESS_BY_KIND.get(document_kind or "report", "internal")


def allowed_levels(role: str) -> Set[str]:
    return ROLE_ACCESS.get(role, {"public"})


def can_access_level(role: str, access_level: str) -> bool:
    return access_level in allowed_levels(role)


def filter_facts(facts: List[Dict[str, Any]], role: str, doc_access: Dict[str, str]) -> List[Dict[str, Any]]:
    if role not in ("external_partner",):
        return facts
    levels = allowed_levels(role)
    result = []
    for f in facts:
        src = f.get("source_document") or ""
        level = doc_access.get(src, "internal")
        if level in levels:
            result.append(f)
    return result


def filter_search_result(result: Dict[str, Any], role: str, doc_access: Dict[str, str]) -> Dict[str, Any]:
    if role not in ("external_partner",):
        return result
    out = dict(result)
    out["verified_facts"] = filter_facts(out.get("verified_facts", []), role, doc_access)
    out["ranked_results"] = [
        r for r in out.get("ranked_results", [])
        if _ranked_allowed(r, doc_access, allowed_levels(role))
    ]
    out["chunks"] = [
        c for c in out.get("chunks", [])
        if doc_access.get(c.get("document", ""), "internal") in allowed_levels(role)
    ]
    if "domestic" in out:
        out["domestic"] = filter_search_result(out["domestic"], role, doc_access)
    if "global" in out:
        out["global"] = filter_search_result(out["global"], role, doc_access)
    return out


def _ranked_allowed(item: Dict[str, Any], doc_access: Dict[str, str], levels: Set[str]) -> bool:
    meta = item.get("metadata") or {}
    src = meta.get("source_document") or meta.get("document") or ""
    if not src and item.get("result_type") == "fact":
        src = (item.get("raw") or {}).get("source_document") or ""
    if not src:
        return item.get("result_type") != "fact"
    return doc_access.get(src, "internal") in levels
