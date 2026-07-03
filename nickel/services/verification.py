"""Верификация: достоверность, provenance, классификация источников."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

INTERNAL_KINDS = {"report", "experiment_catalog"}
PUBLICATION_KINDS = {"publication", "patent"}
REGULATORY_KINDS = {"regulation"}

SOURCE_TYPE_LABELS = {
    "internal_report": "Внутренний отчёт / каталог",
    "publication": "Публикация / патент",
    "regulation": "Нормативный документ",
    "unknown": "Не классифицировано",
}


def source_kind(fact: Dict[str, Any]) -> str:
    props = fact.get("properties") or {}
    kind = props.get("document_kind") or fact.get("document_kind") or "unknown"
    if kind in INTERNAL_KINDS:
        return "internal_report"
    if kind in PUBLICATION_KINDS:
        return "publication"
    if kind in REGULATORY_KINDS:
        return "regulation"
    return "unknown"


def credibility_tier(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Уровень достоверности: tier + score + пояснение."""
    conf = float(fact.get("confidence") or 0.5)
    status = fact.get("verification_status", "pending")
    sk = source_kind(fact)
    props = fact.get("properties") or {}
    has_doi = bool(fact.get("doi") or props.get("doi"))
    has_page = bool(fact.get("source_page") or props.get("source_page") or props.get("page"))
    verified = status == "verified"

    score = conf
    if verified:
        score = min(1.0, conf + 0.15)
    if has_doi:
        score = min(1.0, score + 0.05)
    if has_page:
        score = min(1.0, score + 0.03)
    if sk == "internal_report" and not verified:
        score = max(0.0, score - 0.05)

    if verified and score >= 0.85:
        tier = "high"
        label = "Высокая (верифицировано экспертом)"
    elif verified and score >= 0.65:
        tier = "medium"
        label = "Средняя (верифицировано)"
    elif conf >= 0.75 and has_doi:
        tier = "medium_unverified"
        label = "Средняя, ожидает верификации (есть DOI)"
    elif conf >= 0.5:
        tier = "low"
        label = "Низкая / требует проверки"
    else:
        tier = "uncertain"
        label = "Неопределённая достоверность"

    return {
        "tier": tier,
        "label": label,
        "score": round(score, 3),
        "confidence": conf,
        "verified": verified,
        "source_type": sk,
        "source_type_label": SOURCE_TYPE_LABELS.get(sk, sk),
    }


def build_provenance(fact: Dict[str, Any]) -> Dict[str, Any]:
    props = fact.get("properties") or {}
    page = fact.get("source_page") or props.get("source_page") or props.get("page")
    return {
        "source_document": fact.get("source_document"),
        "doi": fact.get("doi") or props.get("doi"),
        "source_page": page,
        "source_chunk": fact.get("source_chunk") or props.get("source_chunk"),
        "author": props.get("author"),
        "year": props.get("year"),
        "document_kind": props.get("document_kind"),
        "source_type": source_kind(fact),
        "source_excerpt": (props.get("source_excerpt") or "")[:300] or None,
        "job_id": fact.get("job_id"),
    }


def enrich_fact(fact: Dict[str, Any]) -> Dict[str, Any]:
    fact = dict(fact)
    fact["provenance"] = build_provenance(fact)
    fact["credibility"] = credibility_tier(fact)
    fact["source_type"] = source_kind(fact)
    return fact


def aggregate_by_source_type(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    buckets: Dict[str, List[Dict]] = {
        "internal_report": [],
        "publication": [],
        "regulation": [],
        "unknown": [],
    }
    for f in facts:
        buckets[source_kind(f)].append(f)

    summary = {}
    for key, items in buckets.items():
        confs = [float(x.get("confidence") or 0) for x in items]
        verified = sum(1 for x in items if x.get("verification_status") == "verified")
        summary[key] = {
            "label": SOURCE_TYPE_LABELS.get(key, key),
            "count": len(items),
            "verified_count": verified,
            "avg_confidence": round(sum(confs) / len(confs), 3) if confs else 0,
            "with_doi": sum(
                1 for x in items
                if x.get("doi") or (x.get("properties") or {}).get("doi")
            ),
        }
    return summary


def internal_vs_publication_summary(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    internal = [f for f in facts if source_kind(f) == "internal_report"]
    publications = [f for f in facts if source_kind(f) == "publication"]
    regulations = [f for f in facts if source_kind(f) == "regulation"]

    internal_topics = {f["subject"] for f in internal} | {f["object"] for f in internal}
    pub_topics = {f["subject"] for f in publications} | {f["object"] for f in publications}

    return {
        "internal_reports": {
            "count": len(internal),
            "verified": sum(1 for f in internal if f.get("verification_status") == "verified"),
            "sample_facts": [enrich_fact(f) for f in internal[:5]],
        },
        "publications": {
            "count": len(publications),
            "verified": sum(1 for f in publications if f.get("verification_status") == "verified"),
            "with_doi": sum(
                1 for f in publications
                if f.get("doi") or (f.get("properties") or {}).get("doi")
            ),
            "sample_facts": [enrich_fact(f) for f in publications[:5]],
        },
        "regulations": {
            "count": len(regulations),
            "verified": sum(1 for f in regulations if f.get("verification_status") == "verified"),
        },
        "topics_internal_only": sorted(internal_topics - pub_topics)[:15],
        "topics_publication_only": sorted(pub_topics - internal_topics)[:15],
        "shared_topics": sorted(internal_topics & pub_topics)[:15],
    }
