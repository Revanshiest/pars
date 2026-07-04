"""Базовая инфраструктура хранилища: путь к БД, соединение, инициализация схемы."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from services.store import schema


class StoreBase:
    """Общая инфраструктура для доменных миксинов: соединение с SQLite,
    единый лок на запись, инициализация/миграция схемы и метка времени."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("PLATFORM_DB", "data/platform.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._glossary_index_cache: Optional[Dict[str, str]] = None
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
            schema.create_schema(conn)
            schema.migrate_schema(conn)
            schema.create_late_indexes(conn)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
