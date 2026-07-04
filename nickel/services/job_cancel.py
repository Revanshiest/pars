"""Кооперативная отмена задач пайплайна."""

from __future__ import annotations

import threading
from typing import Dict

_lock = threading.Lock()
_flags: Dict[str, threading.Event] = {}


class JobCancelled(Exception):
    """Поднявается из пайплайна при отмене задачи."""


def register(job_id: str) -> None:
    with _lock:
        _flags[job_id] = threading.Event()


def cancel(job_id: str) -> None:
    with _lock:
        ev = _flags.get(job_id)
        if ev:
            ev.set()


def is_cancelled(job_id: str) -> bool:
    with _lock:
        ev = _flags.get(job_id)
        return bool(ev and ev.is_set())


def clear(job_id: str) -> None:
    with _lock:
        _flags.pop(job_id, None)


def check(job_id: str) -> None:
    if is_cancelled(job_id):
        raise JobCancelled("cancelled")
