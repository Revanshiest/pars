"""YandexGPT — единая точка вызова LLM (1 запрос на ответ пользователю)."""

from __future__ import annotations

import os
from typing import List, Optional

from langchain_community.chat_models import ChatYandexGPT
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage


def ensure_yandex_env() -> None:
    key = os.getenv("YANDEX_API_KEY") or os.getenv("YC_API_KEY")
    folder = os.getenv("YANDEX_FOLDER_ID") or os.getenv("YC_FOLDER_ID")
    if key:
        os.environ["YC_API_KEY"] = key.strip("\"'")
    if folder:
        os.environ["YC_FOLDER_ID"] = folder.strip("\"'")


def get_yandex_chat(*, temperature: float = 0.3) -> ChatYandexGPT:
    ensure_yandex_env()
    folder = os.environ.get("YC_FOLDER_ID", "")
    if not folder or not os.environ.get("YC_API_KEY"):
        raise RuntimeError("YANDEX_API_KEY и YANDEX_FOLDER_ID обязательны для чат-бота")
    model = os.getenv("YANDEX_CHAT_MODEL", "yandexgpt/latest")
    return ChatYandexGPT(
        model_uri=f"gpt://{folder}/{model}",
        temperature=temperature,
    )


async def yandex_complete(
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
) -> str:
    """Один запрос к YandexGPT → текст ответа."""
    llm = get_yandex_chat(temperature=temperature)
    messages: List[BaseMessage] = [
        SystemMessage(content=system),
        HumanMessage(content=user),
    ]
    response = await llm.ainvoke(messages)
    content = response.content
    if isinstance(content, list):
        return "".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content or "").strip()
