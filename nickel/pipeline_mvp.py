import json
import asyncio
import os
from typing import List

from ontology.schema import (
    ALLOWED_NODE_TYPES,
    ALLOWED_RELATIONS,
    Triple,
    ExtractionResult,
)
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# =====================================================================
# 2. Интеграция с Ollama (Реальная LLM)
# =====================================================================
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser


class OllamaAPI:
    def __init__(self, model_name: str = "gpt-oss:120b-cloud", base_url: str = "http://localhost:11434"):
        timeout = float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SEC", "600"))
        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            format="json",
            temperature=0,
            timeout=timeout,
        )
        self.parser = JsonOutputParser(pydantic_object=ExtractionResult)

        self.prompt = PromptTemplate(
            template=(
                "Ты - строгий эксперт по извлечению графа знаний (Knowledge Graph Extraction).\n"
                "Твоя задача - извлекать факты в виде троек (субъект, связь, объект) из текста.\n\n"
                "КРИТИЧЕСКИЕ ПРАВИЛА (ШТРАФ ЗА НАРУШЕНИЕ):\n"
                "1. Узлы (subject и object) должны быть МАКСИМАЛЬНО АТОМАРНЫМИ (обычно 1-3 слова).\n"
                "2. Если в предложении много информации, разбей его на несколько независимых, простых троек.\n"
                "3. АББРЕВИАТУРЫ: разворачивай аббревиатуры компаний и локаций. "
                "Исключение: химические элементы (Ni, Co, Fe) — формат 'Символ (Полное название)'.\n"
                "4. ИЗВЛЕКАЙ ТОЛЬКО ЗНАЧИМЫЕ ФАКТЫ предметной области. "
                "Игнорируй оглавления, копирайты, списки литературы.\n"
                "5. Используй строго разрешённые типы связей и узлов. Если связь не подходит — 'related_to'.\n"
                "6. Числовые параметры (концентрации, температуры, скорости) помещай в properties.\n\n"
                "РАЗРЕШЕННЫЕ ТИПЫ УЗЛОВ (subject_type, object_type):\n"
                "{node_types}\n\n"
                "РАЗРЕШЕННЫЕ ТИПЫ СВЯЗЕЙ (relation):\n"
                "{relations}\n\n"
                "ОБЯЗАТЕЛЬНЫЕ ИНСТРУКЦИИ ПО ФОРМАТУ ВЫВОДА:\n{format_instructions}\n\n"
                "Контекст документа (где находится текст): {meta_context}\n"
                "Текст для анализа:\n{text}\n\n"
                "Извлеки АТОМАРНЫЕ факты из текста строго в указанном формате JSON."
            ),
            input_variables=["text", "meta_context"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions(),
                "node_types": ", ".join(ALLOWED_NODE_TYPES),
                "relations": ", ".join(ALLOWED_RELATIONS),
            },
        )

        self.chain = self.prompt | self.llm | self.parser

    async def extract_triples(self, text: str, meta_context: str) -> ExtractionResult:
        try:
            result_dict = await self.chain.ainvoke({"text": text, "meta_context": meta_context})

            valid_triples = []
            for t in result_dict.get("triples", []):
                rel = t.get("relation")
                subj_type = t.get("subject_type")
                obj_type = t.get("object_type")

                if rel in ALLOWED_RELATIONS and subj_type in ALLOWED_NODE_TYPES and obj_type in ALLOWED_NODE_TYPES:
                    valid_triples.append(Triple(**t))
                else:
                    print(f"    ⚠️ Отброшена галлюцинация: {rel} | {subj_type} | {obj_type}")

            return ExtractionResult(triples=valid_triples)
        except Exception as e:
            print(f"❌ Критическая ошибка при парсинге JSON от Ollama: {e}")
            return ExtractionResult(triples=[])


# =====================================================================
# 3. Основной пайплайн
# =====================================================================
async def run_pipeline(filepath: str):
    print(f"Запуск пайплайна для файла: {filepath}\n")
    import os

    if filepath.lower().endswith(".pdf"):
        import pymupdf4llm
        print(f"Конвертация PDF в Markdown: {filepath}...")
        markdown_document = pymupdf4llm.to_markdown(filepath, write_images=False)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_document = f.read()

    headers_to_split_on = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(markdown_document)

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    splits = text_splitter.split_documents(md_header_splits)

    print(f"Документ успешно разбит на {len(splits)} семантических чанков.\n")

    llm = OllamaAPI(model_name="gpt-oss:120b-cloud")
    all_extracted_triples = []

    output_filename = f"{os.path.splitext(filepath)[0]}_extracted.json"

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump({"triples": []}, f, indent=2, ensure_ascii=False)

    batch_size = 3
    delay_between_batches = 2

    async def process_chunk(chunk, chunk_idx):
        metadata = chunk.metadata
        headers_context = " > ".join([v for k, v in metadata.items() if k.startswith("Header")])
        meta_context = f"Файл: {os.path.basename(filepath)} | Раздел: {headers_context}"
        print(f"  [Чанк {chunk_idx}/{len(splits)}] Отправка в модель ({len(chunk.page_content)} симв.)...")
        return await llm.extract_triples(chunk.page_content, meta_context)

    for i in range(0, len(splits), batch_size):
        batch = splits[i : i + batch_size]
        print(f"\n⏳ Обработка батча {i//batch_size + 1}/{(len(splits)-1)//batch_size + 1}")

        tasks = [process_chunk(chunk, i + idx + 1) for idx, chunk in enumerate(batch)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, Exception):
                print(f"❌ Ошибка в чанке: {res}")
            elif isinstance(res, ExtractionResult):
                all_extracted_triples.extend(res.triples)

        final_output = {"triples": [t.model_dump() for t in all_extracted_triples]}
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)
        print(f"💾 Чекпоинт сохранен. Всего троек: {len(all_extracted_triples)}")

        if i + batch_size < len(splits):
            await asyncio.sleep(delay_between_batches)

    print(f"\n✅ Успешно извлечено {len(all_extracted_triples)} троек в файл: {output_filename}")


if __name__ == "__main__":
    import sys
    import glob
    import os

    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.isdir(target):
            test_files = glob.glob(os.path.join(target, "*.pdf"))
        else:
            test_files = [target]
    else:
        test_files = glob.glob("*.pdf")

    if not test_files:
        print("PDF файлы не найдены.")

    for test_file in test_files:
        print(f"\n{'='*60}\n🚀 СТАРТ ПАЙПЛАЙНА ДЛЯ: {test_file}\n{'='*60}\n")
        asyncio.run(run_pipeline(test_file))
