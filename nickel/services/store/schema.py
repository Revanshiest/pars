"""SQLite DDL и миграции для PlatformStore.

Схема БД вынесена сюда без изменений структуры: те же CREATE TABLE,
те же индексы, те же ALTER TABLE миграции, в том же порядке применения.
"""

from __future__ import annotations

import sqlite3


def create_schema(conn: sqlite3.Connection) -> None:
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


def migrate_schema(conn: sqlite3.Connection) -> None:
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
            ("key_prefix", "TEXT"),
        ],
    }
    for table, cols in columns.items():
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, typedef in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typedef}")


def create_late_indexes(conn: sqlite3.Connection) -> None:
    """Индексы по колонкам, которые появляются только после миграций."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_assigned ON verified_facts(assigned_to)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_priority ON verified_facts(review_priority)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_subject ON verified_facts(subject)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_object ON verified_facts(object)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vf_geo ON verified_facts(geography)"
    )
    _ensure_facts_fts(conn)


def _ensure_facts_fts(conn: sqlite3.Connection) -> None:
    """FTS5 для полнотекстового поиска по subject/object/relation."""
    try:
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS verified_facts_fts USING fts5(
                   subject, object, relation, source_document,
                   content='verified_facts', content_rowid='rowid'
               )"""
        )
        count = conn.execute("SELECT COUNT(*) FROM verified_facts_fts").fetchone()[0]
        facts = conn.execute("SELECT COUNT(*) FROM verified_facts").fetchone()[0]
        if facts and count == 0:
            conn.execute(
                """INSERT INTO verified_facts_fts(rowid, subject, object, relation, source_document)
                   SELECT rowid, subject, object, relation, COALESCE(source_document, '')
                   FROM verified_facts"""
            )
        conn.execute(
            """CREATE TRIGGER IF NOT EXISTS verified_facts_ai AFTER INSERT ON verified_facts BEGIN
               INSERT INTO verified_facts_fts(rowid, subject, object, relation, source_document)
               VALUES (new.rowid, new.subject, new.object, new.relation, COALESCE(new.source_document, ''));
               END"""
        )
        conn.execute(
            """CREATE TRIGGER IF NOT EXISTS verified_facts_ad AFTER DELETE ON verified_facts BEGIN
               INSERT INTO verified_facts_fts(verified_facts_fts, rowid, subject, object, relation, source_document)
               VALUES('delete', old.rowid, old.subject, old.object, old.relation, COALESCE(old.source_document, ''));
               END"""
        )
        conn.execute(
            """CREATE TRIGGER IF NOT EXISTS verified_facts_au AFTER UPDATE ON verified_facts BEGIN
               INSERT INTO verified_facts_fts(verified_facts_fts, rowid, subject, object, relation, source_document)
               VALUES('delete', old.rowid, old.subject, old.object, old.relation, COALESCE(old.source_document, ''));
               INSERT INTO verified_facts_fts(rowid, subject, object, relation, source_document)
               VALUES (new.rowid, new.subject, new.object, new.relation, COALESCE(new.source_document, ''));
               END"""
        )
    except sqlite3.OperationalError as exc:
        import logging
        logging.getLogger(__name__).warning("FTS5 setup skipped: %s", exc)
