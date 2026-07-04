"""Выполнение синхронного поиска в thread pool — не блокирует uvicorn event loop."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="search")


async def run_search(fn: Callable[..., Any], *args, **kwargs) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))
