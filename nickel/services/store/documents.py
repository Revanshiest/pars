"""Домен документов: реестр documents и уровни доступа (access_level)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional


class DocumentsMixin:
    """Регистрация документов и управление уровнем доступа.

    Композируется в PlatformStore (использует self._lock, self._connect(),
    self._now())."""

    def register_document(
        self,
        job_id: str,
        source_document: str,
        *,
        document_kind: Optional[str] = None,
        author: Optional[str] = None,
        year: Optional[int] = None,
        geography: Optional[str] = None,
        doi: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        access_level: Optional[str] = None,
    ) -> str:
        from services.access_control import default_access_level

        level = access_level or default_access_level(document_kind)
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{job_id}:{source_document}"))
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO documents
                   (id, job_id, source_document, document_kind, author, year, geography, doi,
                    metadata, access_level, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     document_kind=excluded.document_kind,
                     author=excluded.author,
                     year=excluded.year,
                     geography=excluded.geography,
                     doi=excluded.doi,
                     metadata=excluded.metadata,
                     access_level=excluded.access_level""",
                (
                    doc_id, job_id, source_document, document_kind, author, year,
                    geography, doi, json.dumps(metadata or {}, ensure_ascii=False),
                    level, now,
                ),
            )
        return doc_id

    def get_document_access_map(self) -> Dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT source_document, access_level FROM documents"
            ).fetchall()
            return {
                r["source_document"]: r["access_level"] or "internal"
                for r in rows
            }

    def set_document_access(self, source_document: str, access_level: str) -> bool:
        from services.access_control import ACCESS_LEVELS
        if access_level not in ACCESS_LEVELS:
            raise ValueError(f"Invalid access_level. Allowed: {ACCESS_LEVELS}")
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE documents SET access_level=? WHERE source_document=?",
                (access_level, source_document),
            )
            return cur.rowcount > 0

    def get_document_access(self, source_document: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT access_level FROM documents WHERE source_document=?",
                (source_document,),
            ).fetchone()
            return (row["access_level"] if row else None) or "internal"

    def list_documents(
        self,
        document_kind: Optional[str] = None,
        year: Optional[int] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        author: Optional[str] = None,
        geography: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM documents WHERE 1=1"
        params: list = []
        if document_kind:
            sql += " AND document_kind=?"
            params.append(document_kind)
        if year is not None:
            sql += " AND year=?"
            params.append(year)
        if year_from is not None:
            sql += " AND year >= ?"
            params.append(year_from)
        if year_to is not None:
            sql += " AND year <= ?"
            params.append(year_to)
        if author:
            sql += " AND author LIKE ?"
            params.append(f"%{author}%")
        if geography:
            sql += " AND geography=?"
            params.append(geography)
        sql += " ORDER BY year DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["metadata"] = json.loads(d.get("metadata") or "{}")
                result.append(d)
            return result
