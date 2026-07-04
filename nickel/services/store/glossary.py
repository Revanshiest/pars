"""Домен глоссария: термины, синонимы, индекс нормализации сущностей."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class GlossaryMixin:
    """Глоссарий и его индекс. Композируется в PlatformStore
    (использует self._lock, self._connect(), self._now(),
    self._glossary_index_cache)."""

    def list_glossary(
        self,
        domain: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict]:
        sql = "SELECT * FROM glossary WHERE 1=1"
        params: list = []
        if domain:
            sql += " AND domain=?"
            params.append(domain)
        if q:
            sql += " AND (canonical LIKE ? OR synonyms_ru LIKE ? OR synonyms_en LIKE ? OR definition LIKE ?)"
            params.extend([f"%{q}%"] * 4)
        sql += " ORDER BY canonical LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 1000)), max(0, offset)])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._glossary_row(r) for r in rows]

    def iter_glossary(self) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM glossary ORDER BY canonical").fetchall()
            return [self._glossary_row(r) for r in rows]

    def list_glossary_domains(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT domain FROM glossary WHERE domain IS NOT NULL AND domain != '' ORDER BY domain"
            ).fetchall()
            return [r["domain"] for r in rows]

    def count_glossary(self, domain: Optional[str] = None, q: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) AS c FROM glossary WHERE 1=1"
        params: list = []
        if domain:
            sql += " AND domain=?"
            params.append(domain)
        if q:
            sql += " AND (canonical LIKE ? OR synonyms_ru LIKE ? OR synonyms_en LIKE ? OR definition LIKE ?)"
            params.extend([f"%{q}%"] * 4)
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
            return int(row["c"]) if row else 0

    def _glossary_row(self, row: sqlite3.Row) -> Dict:
        d = dict(row)
        d["synonyms_ru"] = json.loads(d["synonyms_ru"])
        d["synonyms_en"] = json.loads(d["synonyms_en"])
        return d

    def add_glossary_term(self, term: Dict[str, Any], source: str = "manual") -> str:
        tid = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO glossary (id, canonical, synonyms_ru, synonyms_en, domain, definition, source, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    tid, term["canonical"],
                    json.dumps(term.get("synonyms_ru", []), ensure_ascii=False),
                    json.dumps(term.get("synonyms_en", []), ensure_ascii=False),
                    term.get("domain"), term.get("definition"), source, now, now,
                ),
            )
        self._invalidate_glossary_index()
        return tid

    def build_glossary_index(self) -> Dict[str, str]:
        if self._glossary_index_cache is not None:
            return self._glossary_index_cache
        index: Dict[str, str] = {}
        for term in self.iter_glossary():
            canonical = term["canonical"]
            index[canonical.lower()] = canonical
            for syn in term["synonyms_ru"] + term["synonyms_en"]:
                index[syn.lower()] = canonical
        self._glossary_index_cache = index
        return index

    def _invalidate_glossary_index(self):
        self._glossary_index_cache = None

    def seed_glossary_from_file(self, path: Path) -> int:
        if not path.exists():
            return 0
        with open(path, encoding="utf-8") as f:
            terms = json.load(f)
        count = 0
        existing = {t["canonical"].lower() for t in self.iter_glossary()}
        for term in terms:
            if term["canonical"].lower() not in existing:
                self.add_glossary_term(term, source="seed")
                count += 1
        return count
