"""Централизованное логирование платформы."""

from __future__ import annotations

import logging
import os
import sys


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout, force=True)
    for noisy in ("httpx", "httpcore", "urllib3", "neo4j"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
