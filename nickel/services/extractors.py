"""Фабрика экстракторов: Ollama / Yandex."""

from __future__ import annotations

import os
from typing import List, Protocol

from dotenv import load_dotenv

load_dotenv()

if os.getenv("YANDEX_API_KEY"):
    os.environ["YC_API_KEY"] = os.getenv("YANDEX_API_KEY", "").strip("\"'")
if os.getenv("YANDEX_FOLDER_ID"):
    os.environ["YC_FOLDER_ID"] = os.getenv("YANDEX_FOLDER_ID", "").strip("\"'")


class TextExtractor(Protocol):
    async def extract_triples(self, text: str, meta_context: str) -> List[dict]: ...


class OllamaExtractorAdapter:
    def __init__(self):
        from pipeline_mvp import OllamaAPI
        self._api = OllamaAPI(
            model_name=os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    async def extract_triples(self, text: str, meta_context: str) -> List[dict]:
        result = await self._api.extract_triples(text, meta_context)
        return [t.model_dump() for t in result.triples]


class YandexExtractorAdapter:
    def __init__(self):
        from orchestrator import YandexExtractor
        self._api = YandexExtractor()

    async def extract_triples(self, text: str, meta_context: str) -> List[dict]:
        return await self._api.extract_triples(text, meta_context)


def get_text_extractor(backend: str | None = None) -> TextExtractor:
    backend = (backend or os.getenv("EXTRACTOR_BACKEND", "auto")).lower()

    if backend == "yandex":
        if not os.getenv("YANDEX_API_KEY") or not os.getenv("YANDEX_FOLDER_ID"):
            raise RuntimeError("YANDEX_API_KEY and YANDEX_FOLDER_ID required for yandex backend")
        return YandexExtractorAdapter()

    if backend == "ollama":
        return OllamaExtractorAdapter()

    # auto: Yandex if keys present, else Ollama
    if os.getenv("YANDEX_API_KEY") and os.getenv("YANDEX_FOLDER_ID"):
        return YandexExtractorAdapter()
    return OllamaExtractorAdapter()
