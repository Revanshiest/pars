"""Единое SQLite-хранилище: пользователи, глоссарий, верификация, аудит, уведомления."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


ROLES = ["researcher", "analyst", "project_manager", "admin", "external_partner"]

ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "researcher": ["read", "search", "upload", "subscribe", "glossary_read"],
    "analyst": ["read", "search", "upload", "verify", "edit_graph", "export", "subscribe", "glossary_read", "glossary_write", "synthesis"],
    "project_manager": ["read", "search", "upload", "verify", "edit_graph", "export", "dashboard", "compare", "subscribe", "glossary_read", "synthesis", "audit"],
    "admin": ["*"],
    "external_partner": ["read", "search", "glossary_read"],
}


class PlatformStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("PLATFORM_DB", "data/platform.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS glossary (
                    id TEXT PRIMARY KEY,
                    canonical TEXT NOT NULL,
                    synonyms_ru TEXT DEFAULT '[]',
                    synonyms_en TEXT DEFAULT '[]',
                    domain TEXT,
                    definition TEXT,
                    source TEXT DEFAULT 'seed',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_glossary_canonical ON glossary(canonical);
                CREATE TABLE IF NOT EXISTS verified_facts (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    subject_type TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    object TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    properties TEXT DEFAULT '{}',
                    verification_status TEXT DEFAULT 'pending',
                    confidence REAL,
                    geography TEXT,
                    source_document TEXT,
                    verified_by TEXT,
                    verified_at TEXT,
                    notes TEXT,
                    job_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_vf_status ON verified_facts(verification_status);
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    user_role TEXT,
                    action TEXT NOT NULL,
                    resource TEXT,
                    details TEXT,
                    ip TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    filters TEXT DEFAULT '{}',
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notifications (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    read INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_edits (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    before_state TEXT,
                    after_state TEXT,
                    comment TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fact_versions (
                    id TEXT PRIMARY KEY,
                    fact_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    snapshot TEXT NOT NULL,
                    changed_by TEXT,
                    change_reason TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fv_fact ON fact_versions(fact_id);
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    source_document TEXT NOT NULL,
                    document_kind TEXT,
                    author TEXT,
                    year INTEGER,
                    geography TEXT,
                    doi TEXT,
                    metadata TEXT DEFAULT '{}',
                    access_level TEXT DEFAULT 'internal',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_docs_kind ON documents(document_kind);
                CREATE INDEX IF NOT EXISTS idx_docs_year ON documents(year);
                CREATE INDEX IF NOT EXISTS idx_docs_job ON documents(job_id);
            """)
            self._migrate_schema(conn)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vf_assigned ON verified_facts(assigned_to)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_vf_priority ON verified_facts(review_priority)"
            )

    def _migrate_schema(self, conn: sqlite3.Connection):
        columns = {
            "verified_facts": [
                ("source_chunk", "TEXT"),
                ("version", "INTEGER DEFAULT 1"),
                ("doi", "TEXT"),
                ("fair_metadata", "TEXT DEFAULT '{}'"),
                ("shacl_valid", "INTEGER DEFAULT 1"),
                ("assigned_to", "TEXT"),
                ("assigned_at", "TEXT"),
                ("review_priority", "INTEGER DEFAULT 0"),
                ("source_page", "TEXT"),
            ],
            "documents": [
                ("access_level", "TEXT DEFAULT 'internal'"),
            ],
            "api_keys": [
                ("expires_at", "TEXT"),
                ("last_used_at", "TEXT"),
            ],
        }
        for table, cols in columns.items():
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, typedef in cols:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typedef}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _api_key_expires_at() -> str:
        days = int(os.getenv("API_KEY_TTL_DAYS", "90"))
        exp = datetime.now(timezone.utc) + timedelta(days=days)
        return exp.isoformat()

    def count_users(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]

    def count_admins(self) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
            ).fetchone()["c"]

    def create_user(
        self,
        email: str,
        name: str,
        role: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        email = email.strip().lower()
        if "@" not in email:
            raise ValueError("Invalid email")
        if role not in ROLES:
            raise ValueError(f"Unknown role '{role}'. Allowed: {ROLES}")

        key = (api_key or self._generate_api_key()).strip()
        if len(key) < 16:
            raise ValueError("API key must be at least 16 characters")

        uid = str(uuid.uuid4())
        now = self._now()
        with self._lock, self._connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise ValueError(f"Email already registered: {email}")
            conn.execute(
                "INSERT INTO users (id, email, name, role, created_at) VALUES (?,?,?,?,?)",
                (uid, email, name.strip(), role, now),
            )
            conn.execute(
                "INSERT INTO api_keys (key, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (key, uid, now, self._api_key_expires_at()),
            )
        return {
            "id": uid,
            "email": email,
            "name": name.strip(),
            "role": role,
            "created_at": now,
            "api_key": key,
        }

    def update_user(
        self,
        user_id: str,
        *,
        name: Optional[str] = None,
        role: Optional[str] = None,
        email: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return None

            current = dict(row)
            new_role = role if role is not None else current["role"]
            if new_role not in ROLES:
                raise ValueError(f"Unknown role '{new_role}'. Allowed: {ROLES}")

            if current["role"] == "admin" and new_role != "admin":
                admin_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
                ).fetchone()["c"]
                if admin_count <= 1:
                    raise ValueError("Cannot demote the last admin")

            new_email = email.strip().lower() if email else current["email"]
            if new_email != current["email"]:
                dup = conn.execute(
                    "SELECT 1 FROM users WHERE email=? AND id!=?", (new_email, user_id)
                ).fetchone()
                if dup:
                    raise ValueError(f"Email already registered: {new_email}")

            conn.execute(
                "UPDATE users SET email=?, name=?, role=? WHERE id=?",
                (
                    new_email,
                    name.strip() if name is not None else current["name"],
                    new_role,
                    user_id,
                ),
            )
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                return False
            if row["role"] == "admin":
                admin_count = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE role='admin'"
                ).fetchone()["c"]
                if admin_count <= 1:
                    raise ValueError("Cannot delete the last admin")
            conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        return True

    def rotate_api_key(self, user_id: str) -> Optional[str]:
        key = self._generate_api_key()
        now = self._now()
        with self._lock, self._connect() as conn:
            if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone():
                return None
            conn.execute("DELETE FROM api_keys WHERE user_id=?", (user_id,))
            conn.execute(
                "INSERT INTO api_keys (key, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                (key, user_id, now, self._api_key_expires_at()),
            )
        return key

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, name, role, created_at FROM users WHERE id=?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_users(self) -> List[Dict[str, Any]]:
        return self.list_users_detailed()

    def list_users_detailed(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT u.id, u.email, u.name, u.role, u.created_at,
                          k.key, k.created_at AS key_created_at
                   FROM users u
                   LEFT JOIN api_keys k ON k.user_id = u.id
                   ORDER BY u.email"""
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                key = d.pop("key", None)
                d["key_hint"] = f"...{key[-4:]}" if key and len(key) >= 4 else None
                result.append(d)
            return result

    def list_roles(self) -> List[Dict[str, Any]]:
        return [
            {"role": role, "permissions": perms}
            for role, perms in ROLE_PERMISSIONS.items()
        ]

    def auth_status(self) -> Dict[str, Any]:
        count = self.count_users()
        return {
            "setup_required": count == 0,
            "users_count": count,
            "roles": ROLES,
        }

    @staticmethod
    def _generate_api_key() -> str:
        return secrets.token_urlsafe(32)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, email, name, role FROM users WHERE email=?",
                (email.strip().lower(),),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        now = self._now()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """SELECT u.id, u.email, u.name, u.role, k.expires_at
                   FROM users u JOIN api_keys k ON k.user_id = u.id WHERE k.key=?""",
                (api_key,),
            ).fetchone()
            if not row:
                return None
            if row["expires_at"] and row["expires_at"] < now:
                return None
            conn.execute(
                "UPDATE api_keys SET last_used_at=? WHERE key=?",
                (now, api_key),
            )
            return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}

    def has_permission(self, role: str, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(role, [])
        return "*" in perms or permission in perms

    def audit(self, user: Optional[Dict], action: str, resource: str = "", details: Optional[dict] = None, ip: str = ""):
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO audit_log (id, user_id, user_role, action, resource, details, ip, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    user["id"] if user else None,
                    user["role"] if user else None,
                    action,
                    resource,
                    json.dumps(details or {}, ensure_ascii=False),
                    ip,
                    self._now(),
                ),
            )

    def list_glossary(self, domain: Optional[str] = None, q: Optional[str] = None) -> List[Dict]:
        sql = "SELECT * FROM glossary WHERE 1=1"
        params: list = []
        if domain:
            sql += " AND domain=?"
            params.append(domain)
        if q:
            sql += " AND (canonical LIKE ? OR synonyms_ru LIKE ? OR synonyms_en LIKE ?)"
            params.extend([f"%{q}%"] * 3)
        sql += " ORDER BY canonical"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._glossary_row(r) for r in rows]

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
        return tid

    def build_glossary_index(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for term in self.list_glossary():
            canonical = term["canonical"]
            index[canonical.lower()] = canonical
            for syn in term["synonyms_ru"] + term["synonyms_en"]:
                index[syn.lower()] = canonical
        return index

    def seed_glossary_from_file(self, path: Path) -> int:
        if not path.exists():
            return 0
        with open(path, encoding="utf-8") as f:
            terms = json.load(f)
        count = 0
        existing = {t["canonical"].lower() for t in self.list_glossary()}
        for term in terms:
            if term["canonical"].lower() not in existing:
                self.add_glossary_term(term, source="seed")
                count += 1
        return count

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
        limit: int = 100,
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
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            facts = [self._fact_row(r) for r in rows]
        if query:
            q = query.lower()
            facts = [
                f for f in facts
                if q in f["subject"].lower()
                or q in f["object"].lower()
                or q in f["relation"].lower()
                or q in (f.get("source_document") or "").lower()
            ]
        return facts

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

    def create_notification(self, user_id: str, title: str, body: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO notifications (id, user_id, title, body, read, created_at) VALUES (?,?,?,?,0,?)",
                (str(uuid.uuid4()), user_id, title, body, self._now()),
            )

    def list_notifications(self, user_id: str, unread_only: bool = False) -> List[Dict]:
        sql = "SELECT * FROM notifications WHERE user_id=?"
        params: list = [user_id]
        if unread_only:
            sql += " AND read=0"
        sql += " ORDER BY created_at DESC LIMIT 50"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def mark_notification_read(self, notification_id: str, user_id: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE notifications SET read=1 WHERE id=? AND user_id=?",
                (notification_id, user_id),
            )

    def add_subscription(self, user_id: str, topic: str, filters: Optional[dict] = None) -> str:
        sid = str(uuid.uuid4())
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO subscriptions (id, user_id, topic, filters, active, created_at) VALUES (?,?,?,?,1,?)",
                (sid, user_id, topic, json.dumps(filters or {}), self._now()),
            )
        return sid

    def list_subscriptions(self, user_id: str) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM subscriptions WHERE user_id=? AND active=1", (user_id,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["filters"] = json.loads(d["filters"])
                result.append(d)
            return result

    def notify_subscribers(self, topic_keywords: List[str], title: str, body: str):
        with self._connect() as conn:
            subs = conn.execute("SELECT * FROM subscriptions WHERE active=1").fetchall()
            for sub in subs:
                topic = sub["topic"].lower()
                if any(kw.lower() in topic or topic in kw.lower() for kw in topic_keywords):
                    self.create_notification(sub["user_id"], title, body)

    def log_graph_edit(self, user_id: str, action: str, before: Optional[dict], after: Optional[dict], comment: str = ""):
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO graph_edits (id, user_id, action, before_state, after_state, comment, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), user_id, action,
                    json.dumps(before, ensure_ascii=False) if before else None,
                    json.dumps(after, ensure_ascii=False) if after else None,
                    comment, self._now(),
                ),
            )

    def list_graph_edits(self, limit: int = 50) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM graph_edits ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if d.get("before_state"):
                    d["before_state"] = json.loads(d["before_state"])
                if d.get("after_state"):
                    d["after_state"] = json.loads(d["after_state"])
                result.append(d)
            return result

    def audit_log_list(self, limit: int = 100) -> List[Dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["details"] = json.loads(d["details"]) if d.get("details") else {}
                result.append(d)
            return result

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


_store: Optional[PlatformStore] = None


def get_store() -> PlatformStore:
    global _store
    if _store is None:
        _store = PlatformStore()
    return _store
