"""Хранилище задач пайплайна (SQLite) + append-only логи."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


ACTIVE_STATUSES = (JobStatus.PENDING.value, JobStatus.RUNNING.value)
TERMINAL_STATUSES = (JobStatus.COMPLETED.value, JobStatus.FAILED.value)


class JobStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("JOBS_DB") or "data/jobs.db"
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    stage TEXT,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    message TEXT,
                    result TEXT,
                    error TEXT,
                    job_type TEXT DEFAULT 'single',
                    batch_id TEXT,
                    folder_path TEXT,
                    created_by TEXT,
                    files_total INTEGER DEFAULT 0,
                    files_done INTEGER DEFAULT 0,
                    files_failed INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    level TEXT DEFAULT 'info',
                    stage TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_logs_job ON job_logs(job_id, id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_batch ON jobs(batch_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
            )
            self._migrate_jobs(conn)

    def _migrate_jobs(self, conn: sqlite3.Connection):
        existing = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        for col, typedef in (
            ("job_type", "TEXT DEFAULT 'single'"),
            ("batch_id", "TEXT"),
            ("folder_path", "TEXT"),
            ("created_by", "TEXT"),
            ("files_total", "INTEGER DEFAULT 0"),
            ("files_done", "INTEGER DEFAULT 0"),
            ("files_failed", "INTEGER DEFAULT 0"),
        ):
            if col not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {typedef}")

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def append_log(
        self,
        job_id: str,
        message: str,
        *,
        stage: Optional[str] = None,
        level: str = "info",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO job_logs (job_id, level, stage, message, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, level, stage, message, now),
            )
            return int(cur.lastrowid)

    def get_logs(
        self,
        job_id: str,
        *,
        since_id: int = 0,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT id, job_id, level, stage, message, created_at
                   FROM job_logs WHERE job_id=? AND id>? ORDER BY id ASC LIMIT ?""",
                (job_id, since_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def create_job(
        self,
        filename: str,
        filepath: str,
        *,
        job_type: str = "single",
        batch_id: Optional[str] = None,
        folder_path: Optional[str] = None,
        created_by: Optional[str] = None,
        files_total: int = 0,
    ) -> str:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs (
                       id, filename, filepath, status, job_type, batch_id, folder_path,
                       created_by, files_total, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    filename,
                    filepath,
                    JobStatus.PENDING.value,
                    job_type,
                    batch_id,
                    folder_path,
                    created_by,
                    files_total,
                    now,
                    now,
                ),
            )
        self.append_log(job_id, f"Задача создана: {filename}", level="info")
        return job_id

    def update_progress(
        self,
        job_id: str,
        stage: str,
        current: int,
        total: int,
        message: Optional[str] = None,
        status: JobStatus = JobStatus.RUNNING,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] in TERMINAL_STATUSES:
                return
            conn.execute(
                """UPDATE jobs SET status=?, stage=?, progress_current=?, progress_total=?,
                   message=?, updated_at=? WHERE id=?""",
                (status.value, stage, current, total, message, now, job_id),
            )
        if message:
            self.append_log(job_id, message, stage=stage)

    def complete_job(self, job_id: str, result: Dict[str, Any]):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] in TERMINAL_STATUSES:
                return
            conn.execute(
                """UPDATE jobs SET status=?, result=?, updated_at=?, stage='done',
                   progress_current=1, progress_total=1, message=? WHERE id=?""",
                (
                    JobStatus.COMPLETED.value,
                    json.dumps(result, ensure_ascii=False),
                    now,
                    "Обработка завершена успешно",
                    job_id,
                ),
            )
        self.append_log(job_id, "Обработка завершена успешно", stage="done", level="success")

    def fail_job(self, job_id: str, error: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] in TERMINAL_STATUSES:
                return
            conn.execute(
                """UPDATE jobs SET status=?, error=?, updated_at=?, message=? WHERE id=?""",
                (JobStatus.FAILED.value, error, now, error, job_id),
            )
        self.append_log(job_id, error, level="error")

    def cancel_job(self, job_id: str, reason: str = "Отменено пользователем") -> bool:
        job = self.get_job(job_id)
        if not job:
            return False
        if job["status"] not in ACTIVE_STATUSES:
            return False
        self.fail_job(job_id, reason)
        return True

    def reconcile_stale_jobs(self, reason: str = "Прервано перезапуском сервиса") -> int:
        """Пометить зависшие pending/running задачи как failed (после рестарта API)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status IN (?, ?)",
                (JobStatus.PENDING.value, JobStatus.RUNNING.value),
            ).fetchall()
            if not rows:
                return 0
            ids = [r["id"] for r in rows]
            conn.execute(
                """UPDATE jobs SET status=?, error=?, message=?, updated_at=?
                   WHERE status IN (?, ?)""",
                (JobStatus.FAILED.value, reason, reason, now, JobStatus.PENDING.value, JobStatus.RUNNING.value),
            )
        for jid in ids:
            self.append_log(jid, reason, level="warning")
        return len(ids)

    def update_batch_stats(self, batch_id: str, done: int, failed: int, total: int):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """UPDATE jobs SET files_done=?, files_failed=?, files_total=?,
                   progress_current=?, progress_total=?, updated_at=? WHERE id=?""",
                (done, failed, total, done + failed, total, now, batch_id),
            )

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            return self._row_to_dict(row) if row else None

    def list_jobs(
        self,
        limit: int = 50,
        *,
        active_only: bool = False,
        batch_id: Optional[str] = None,
        job_type: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM jobs WHERE 1=1"
        params: list = []
        if active_only:
            sql += " AND status IN (?, ?)"
            params.extend(ACTIVE_STATUSES)
        if batch_id:
            sql += " AND batch_id=?"
            params.append(batch_id)
        if job_type:
            sql += " AND job_type=?"
            params.append(job_type)
        if created_by:
            sql += " AND created_by=?"
            params.append(created_by)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        if d.get("result"):
            d["result"] = json.loads(d["result"])
        return d
