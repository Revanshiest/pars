"""Домен фактов: verified_facts, версии (fact_versions), верификация и очередь."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any, Dict, List, Optional


class FactsMixin:
    """Работа с verified_facts и fact_versions: upsert, версии, верификация,
    назначение экспертам, очередь, поиск. Композируется в PlatformStore
    (использует self._lock, self._connect(), self._now(), а также
    self.get_document_access_map() из DocumentsMixin)."""

    @staticmethod
    def _fact_id(triple: Dict) -> str:
        return str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{triple['subject']}:{triple['relation']}:{triple['object']}",
        ))

    @staticmethod
    def _snapshot(triple: Dict) -> str:
        payload = {
            k: triple.get(k)
            for k in (
                "subject", "subject_type", "relation", "object", "object_type",
                "properties", "source_chunk", "confidence", "geography",
                "verification_status", "version",
            )
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def upsert_facts(
        self,
        triples: List[Dict],
        job_id: str,
        source_document: str,
        shacl_valid: bool = True,
        changed_by: Optional[str] = None,
    ):
        now = self._now()
        with self._lock, self._connect() as conn:
            for t in triples:
                fid = self._fact_id(t)
                t["fact_id"] = fid
                props = t.get("properties") or {}
                doi = props.get("doi")
                fair = props.get("fair") or {}
                source_chunk = t.get("source_chunk") or props.get("source_chunk")
                source_page = t.get("source_page") or props.get("source_page") or props.get("page")
                if source_page is not None:
                    props.setdefault("source_page", source_page)

                existing = conn.execute(
                    "SELECT * FROM verified_facts WHERE id=?", (fid,)
                ).fetchone()

                version = 1
                if existing:
                    ex = dict(existing)
                    old_ver = ex.get("version") or 1
                    old_snapshot = self._snapshot({
                        "subject": ex["subject"],
                        "subject_type": ex["subject_type"],
                        "relation": ex["relation"],
                        "object": ex["object"],
                        "object_type": ex["object_type"],
                        "properties": json.loads(ex["properties"]),
                        "source_chunk": ex.get("source_chunk"),
                        "confidence": ex.get("confidence"),
                        "geography": ex.get("geography"),
                        "verification_status": ex.get("verification_status"),
                        "version": old_ver,
                    })
                    new_snapshot = self._snapshot({**t, "version": old_ver})
                    if old_snapshot != new_snapshot:
                        version = old_ver + 1
                        conn.execute(
                            """INSERT INTO fact_versions (id, fact_id, version, snapshot, changed_by, change_reason, created_at)
                               VALUES (?,?,?,?,?,?,?)""",
                            (
                                str(uuid.uuid4()), fid, old_ver, old_snapshot,
                                changed_by, "pipeline_update", now,
                            ),
                        )
                    else:
                        version = old_ver

                t["version"] = version

                conn.execute(
                    """INSERT INTO verified_facts
                       (id, subject, subject_type, relation, object, object_type, properties,
                        verification_status, confidence, geography, source_document, job_id,
                        source_chunk, version, doi, fair_metadata, shacl_valid,
                        source_page, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                         subject=excluded.subject,
                         object=excluded.object,
                         properties=excluded.properties,
                         confidence=excluded.confidence,
                         geography=excluded.geography,
                         source_chunk=excluded.source_chunk,
                         version=excluded.version,
                         doi=excluded.doi,
                         fair_metadata=excluded.fair_metadata,
                         shacl_valid=excluded.shacl_valid,
                         source_page=excluded.source_page,
                         updated_at=excluded.updated_at""",
                    (
                        fid, t["subject"], t["subject_type"], t["relation"],
                        t["object"], t["object_type"],
                        json.dumps(props, ensure_ascii=False),
                        t.get("verification_status", "pending"),
                        t.get("confidence"), t.get("geography"),
                        source_document, job_id,
                        source_chunk, version, doi,
                        json.dumps(fair, ensure_ascii=False),
                        1 if shacl_valid else 0,
                        str(source_page) if source_page is not None else None,
                        now, now,
                    ),
                )

    def get_fact_versions(self, fact_id: str) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM fact_versions WHERE fact_id=? ORDER BY version DESC",
                (fact_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["snapshot"] = json.loads(d["snapshot"])
                result.append(d)
            return result

    def verify_fact(self, fact_id: str, status: str, user_id: str, notes: str = "") -> bool:
        now = self._now()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM verified_facts WHERE id=?", (fact_id,)).fetchone()
            if not row:
                return False

            fact = self._fact_row(row)
            if status in ("verified", "rejected"):
                conn.execute(
                    """UPDATE verified_facts
                       SET verification_status=?, verified_by=?, verified_at=?, notes=?,
                           assigned_to=NULL, assigned_at=NULL, updated_at=?
                       WHERE id=?""",
                    (status, user_id, now, notes, now, fact_id),
                )
            else:
                conn.execute(
                    """UPDATE verified_facts
                       SET verification_status=?, notes=?, updated_at=?
                       WHERE id=?""",
                    (status, notes, now, fact_id),
                )

            conn.execute(
                """INSERT INTO fact_versions (id, fact_id, version, snapshot, changed_by, change_reason, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), fact_id,
                    fact.get("version", 1),
                    self._snapshot({**fact, "verification_status": status}),
                    user_id, f"verify:{status}", now,
                ),
            )

        if status == "rejected":
            try:
                from services.neo4j_loader import Neo4jLoader
                with Neo4jLoader() as loader:
                    loader.delete_fact({**fact, "id": fact_id})
            except Exception:
                pass
        return True

    def assign_fact(
        self,
        fact_id: str,
        expert_id: str,
        priority: int = 0,
        assigner_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        now = self._now()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM verified_facts WHERE id=? AND verification_status='pending'",
                (fact_id,),
            ).fetchone()
            if not row:
                return None
            if not conn.execute("SELECT id FROM users WHERE id=?", (expert_id,)).fetchone():
                raise ValueError("Expert user not found")
            conn.execute(
                """UPDATE verified_facts
                   SET assigned_to=?, assigned_at=?, review_priority=?, updated_at=?
                   WHERE id=?""",
                (expert_id, now, priority, now, fact_id),
            )
        return self.get_fact(fact_id)

    def unassign_fact(self, fact_id: str) -> bool:
        now = self._now()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """UPDATE verified_facts
                   SET assigned_to=NULL, assigned_at=NULL, updated_at=?
                   WHERE id=? AND verification_status='pending'""",
                (now, fact_id),
            )
            return cur.rowcount > 0

    def claim_verification_tasks(self, expert_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        now = self._now()
        claimed: List[str] = []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """SELECT id FROM verified_facts
                   WHERE verification_status='pending' AND assigned_to IS NULL
                   ORDER BY review_priority DESC, created_at ASC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            for row in rows:
                fid = row["id"]
                conn.execute(
                    """UPDATE verified_facts
                       SET assigned_to=?, assigned_at=?, updated_at=?
                       WHERE id=? AND assigned_to IS NULL""",
                    (expert_id, now, now, fid),
                )
                claimed.append(fid)
        return [f for fid in claimed if (f := self.get_fact(fid))]

    def list_verification_queue(
        self,
        *,
        assigned_to: Optional[str] = None,
        unassigned_only: bool = False,
        min_priority: Optional[int] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        sql = "SELECT * FROM verified_facts WHERE verification_status='pending'"
        params: list = []
        if unassigned_only:
            sql += " AND assigned_to IS NULL"
        if assigned_to:
            sql += " AND assigned_to=?"
            params.append(assigned_to)
        if min_priority is not None:
            sql += " AND review_priority >= ?"
            params.append(min_priority)
        sql += " ORDER BY review_priority DESC, created_at ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            facts = [self._fact_row(r) for r in rows]
        with self._connect() as conn:
            total_pending = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='pending'"
            ).fetchone()["c"]
            unassigned = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_facts WHERE verification_status='pending' AND assigned_to IS NULL"
            ).fetchone()["c"]
        return {
            "total_pending": total_pending,
            "unassigned": unassigned,
            "items": facts,
        }

    def _fact_row_light(self, row: sqlite3.Row) -> Dict:
        """Строка факта без enrich_fact — для быстрого обхода графа."""
        d = dict(row)
        d["properties"] = json.loads(d["properties"])
        return d

    def _entity_match_terms(self, entity_name: str, *, max_terms: int = 8) -> List[str]:
        raw = entity_name.strip()
        if not raw:
            return []
        terms = {raw.lower()}
        idx = getattr(self, "_glossary_index_cache", None)
        if idx is not None:
            canon = idx.get(raw.lower())
            if canon:
                terms.add(canon.lower())
        else:
            for t in self.list_glossary(q=raw, limit=4):
                canonical = (t.get("canonical") or "").strip()
                if canonical:
                    terms.add(canonical.lower())
                for syn in (t.get("synonyms_ru") or [])[:3] + (t.get("synonyms_en") or [])[:3]:
                    if syn:
                        terms.add(str(syn).lower())
        return [t for t in terms if t][:max_terms]

    def list_entity_neighbor_facts(
        self,
        entity_name: str,
        *,
        limit: int = 24,
        role: Optional[str] = None,
    ) -> List[Dict]:
        """Соседи сущности в графе: один SQL-запрос, без enrich_fact."""
        terms = self._entity_match_terms(entity_name)
        if not terms:
            return []

        match_sql = " OR ".join(
            "(LOWER(subject) LIKE ? OR LOWER(object) LIKE ?)" for _ in terms
        )
        params: list = []
        for term in terms:
            pat = f"%{term}%"
            params.extend([pat, pat])

        sql = f"SELECT * FROM verified_facts WHERE ({match_sql})"
        if role == "external_partner":
            access_map = self.get_document_access_map()
            allowed = [s for s, lvl in access_map.items() if lvl in ("partner", "public")]
            if not allowed:
                return []
            placeholders = ",".join("?" * len(allowed))
            sql += f" AND source_document IN ({placeholders})"
            params.extend(allowed)

        sql += " ORDER BY COALESCE(confidence, 0) DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(limit, 120)))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._fact_row_light(r) for r in rows]

    def list_facts(
        self,
        status: Optional[str] = None,
        geography: Optional[str] = None,
        min_confidence: Optional[float] = None,
        year: Optional[int] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
        document_kind: Optional[str] = None,
        source_document: Optional[str] = None,
        job_id: Optional[str] = None,
        query: Optional[str] = None,
        role: Optional[str] = None,
        limit: Optional[int] = 100,
        light: bool = False,
    ) -> List[Dict]:
        sql = "SELECT * FROM verified_facts WHERE 1=1"
        params: list = []
        if role == "external_partner":
            access_map = self.get_document_access_map()
            allowed = [s for s, lvl in access_map.items() if lvl in ("partner", "public")]
            if not allowed:
                return []
            placeholders = ",".join("?" * len(allowed))
            sql += f" AND source_document IN ({placeholders})"
            params.extend(allowed)
        if status:
            sql += " AND verification_status=?"
            params.append(status)
        if geography:
            sql += " AND geography=?"
            params.append(geography)
        if min_confidence is not None:
            sql += " AND confidence >= ?"
            params.append(min_confidence)
        if source_document:
            sql += " AND source_document=?"
            params.append(source_document)
        if job_id:
            sql += " AND job_id=?"
            params.append(job_id)
        if year is not None:
            sql += " AND CAST(json_extract(properties, '$.year') AS INTEGER)=?"
            params.append(year)
        if year_from is not None:
            sql += " AND CAST(json_extract(properties, '$.year') AS INTEGER) >= ?"
            params.append(year_from)
        if year_to is not None:
            sql += " AND CAST(json_extract(properties, '$.year') AS INTEGER) <= ?"
            params.append(year_to)
        if author:
            sql += " AND json_extract(properties, '$.author') LIKE ?"
            params.append(f"%{author}%")
        if document_kind:
            sql += " AND json_extract(properties, '$.document_kind')=?"
            params.append(document_kind)
        if query:
            qpat = f"%{query.lower()}%"
            sql += (
                " AND (LOWER(subject) LIKE ? OR LOWER(object) LIKE ?"
                " OR LOWER(relation) LIKE ? OR LOWER(COALESCE(source_document, '')) LIKE ?"
                " OR LOWER(COALESCE(json_extract(properties, '$.description'), '')) LIKE ?"
                " OR LOWER(COALESCE(json_extract(properties, '$.value'), '')) LIKE ?)"
            )
            params.extend([qpat, qpat, qpat, qpat, qpat, qpat])
        sql += " ORDER BY updated_at DESC"
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            parse = self._fact_row_light if light else self._fact_row
            return [parse(r) for r in rows]

    def search_facts(
        self,
        query: str,
        *,
        expanded_query: Optional[str] = None,
        limit: int = 100,
        **filters,
    ) -> List[Dict]:
        """Поиск фактов: сначала целая фраза, затем по ключевым словам."""
        from services.query_tokens import extract_search_terms

        facts = self.list_facts(query=query, limit=limit, **filters)
        if facts:
            return facts

        terms = extract_search_terms(query, expanded_query or "")
        if not terms:
            return []

        seen: set[str] = set()
        ranked: List[tuple[int, Dict]] = []

        for term in terms:
            batch = self.list_facts(query=term, limit=limit, **filters)
            for f in batch:
                fid = f.get("id") or ""
                if fid in seen:
                    continue
                seen.add(fid)
                score = 0
                subj = (f.get("subject") or "").lower()
                obj = (f.get("object") or "").lower()
                props = f.get("properties") or {}
                desc = str(props.get("description") or "").lower()
                val = str(props.get("value") or "").lower()
                for t in terms:
                    if t in subj or t in obj:
                        score += 3
                    elif t in desc or t in val:
                        score += 2
                    elif t in (f.get("relation") or "").lower():
                        score += 1
                ranked.append((score, f))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in ranked[:limit]]

    def _fact_row(self, row: sqlite3.Row) -> Dict:
        from services.verification import enrich_fact

        d = dict(row)
        d["properties"] = json.loads(d["properties"])
        if d.get("fair_metadata"):
            try:
                d["fair_metadata"] = json.loads(d["fair_metadata"])
            except Exception:
                pass
        return enrich_fact(d)

    def get_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM verified_facts WHERE id=?", (fact_id,)).fetchone()
            return self._fact_row(row) if row else None
