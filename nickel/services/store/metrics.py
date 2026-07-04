"""Агрегированные метрики для дашборда (по фактам и глоссарию)."""

from __future__ import annotations

from typing import Any, Dict


class MetricsMixin:
    """Сводные показатели платформы. Композируется в PlatformStore
    (использует self._connect())."""

    def dashboard_metrics(self) -> Dict[str, Any]:
        with self._connect() as conn:
            facts_total = conn.execute("SELECT COUNT(*) AS c FROM verified_facts").fetchone()["c"]
            verified = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='verified'"
            ).fetchone()["c"]
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='pending'"
            ).fetchone()["c"]
            assigned_pending = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='pending' AND assigned_to IS NOT NULL"
            ).fetchone()["c"]
            contradictions = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE relation='contradicts'"
            ).fetchone()["c"]
            glossary_count = conn.execute("SELECT COUNT(*) AS c FROM glossary").fetchone()["c"]
            by_domain = conn.execute(
                "SELECT domain, COUNT(*) AS c FROM glossary GROUP BY domain"
            ).fetchall()
            by_geo = conn.execute(
                "SELECT geography, COUNT(*) AS c FROM verified_facts WHERE geography IS NOT NULL GROUP BY geography"
            ).fetchall()
            by_type = conn.execute(
                "SELECT subject_type, COUNT(*) AS c FROM verified_facts GROUP BY subject_type ORDER BY c DESC"
            ).fetchall()
            low_coverage = conn.execute(
                """SELECT subject_type, COUNT(*) AS c FROM verified_facts
                   GROUP BY subject_type HAVING c < 5"""
            ).fetchall()
        return {
            "facts_total": facts_total,
            "verified": verified,
            "pending_verification": pending,
            "assigned_in_queue": assigned_pending,
            "contradictions": contradictions,
            "glossary_terms": glossary_count,
            "glossary_by_domain": {r["domain"]: r["c"] for r in by_domain},
            "facts_by_geography": {r["geography"]: r["c"] for r in by_geo},
            "facts_by_entity_type": {r["subject_type"]: r["c"] for r in by_type},
            "risk_zones_low_coverage": [dict(r) for r in low_coverage],
        }
