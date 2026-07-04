"""Агрегированные метрики для дашборда (по фактам, глоссарию и доменам)."""

from __future__ import annotations

from typing import Any, Dict, List

from services.platform_config import domains_config


class MetricsMixin:
    """Сводные показатели платформы. Композируется в PlatformStore
    (использует self._connect())."""

    def _compute_domain_coverage(self, conn) -> Dict[str, Dict[str, Any]]:
        coverage: Dict[str, Dict[str, Any]] = {}
        for domain_key, meta in (domains_config().get("domains") or {}).items():
            label = meta.get("label", domain_key)
            processes = list(meta.get("processes") or [])

            matched = 0
            fact_hits = 0
            for proc in processes:
                pattern = f"%{proc.lower()}%"
                row = conn.execute(
                    """SELECT COUNT(*) AS c FROM verified_facts
                       WHERE LOWER(subject) LIKE ? OR LOWER(object) LIKE ?""",
                    (pattern, pattern),
                ).fetchone()
                cnt = int(row["c"]) if row else 0
                if cnt > 0:
                    matched += 1
                    fact_hits += cnt

            total = len(processes) or 1
            coverage[domain_key] = {
                "label": label,
                "processes_total": len(processes),
                "processes_covered": matched,
                "facts_matched": fact_hits,
                "coverage_ratio": round(matched / total, 2) if processes else 0.0,
                "risk": matched < max(1, len(processes) // 2),
            }
        return coverage

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
            domain_coverage = self._compute_domain_coverage(conn)

        risk_domains = [
            {"domain": k, **v} for k, v in domain_coverage.items() if v.get("risk")
        ]
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
            "domain_coverage": domain_coverage,
            "risk_domains": risk_domains,
        }
