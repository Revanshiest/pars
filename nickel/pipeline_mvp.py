import json
import asyncio
from typing import List, Literal
from pydantic import BaseModel, Field
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# =====================================================================
# 1. Онтология предметной области (Pydantic схемы для Structured Output)
# =====================================================================

# Разрешенные типы для подсказки модели
ALLOWED_NODE_TYPES = [
    "Material", "Equipment", "Process", "Parameter", "Metric", 
    "Property", "Facility", "Expert", "Regulation", "Publication",
    "Geography", "Document", "Concept"
]

ALLOWED_RELATIONS = [
    "uses_material", "operates_at_condition", "produces_output", 
    "described_in", "validated_by", "contradicts",
    "located_in", "has_property", "part_of", "managed_by", "related_to"
]

NodeType = str
RelationType = str

class Triple(BaseModel):
    subject: str = Field(description="Имя субъекта (исходного узла)")
    subject_type: NodeType = Field(description="Тип субъекта из онтологии")
    relation: RelationType = Field(description="Тип связи из онтологии")
    object: str = Field(description="Имя объекта (целевого узла)")
    object_type: NodeType = Field(description="Тип объекта из онтологии")

class ExtractionResult(BaseModel):
    triples: List[Triple] = Field(description="Список извлеченных троек (фактов)")

# =====================================================================
# 2. Интеграция с Ollama (Реальная LLM)
# =====================================================================
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

class OllamaAPI:
    def __init__(self, model_name: str = "gpt-oss:120b-cloud", base_url: str = "http://localhost:11434"):
        # Инициализируем модель Ollama. format="json" гарантирует, что модель вернет валидный JSON
        self.llm = ChatOllama(model=model_name, base_url=base_url, format="json", temperature=0)
        
        # Парсер, который сгенерирует инструкции для LLM на основе нашей Pydantic схемы
        self.parser = JsonOutputParser(pydantic_object=ExtractionResult)
        
        # Промпт для извлечения троек с жестким указанием формата и атомарности
        self.prompt = PromptTemplate(
            template=(
                "Ты - строгий эксперт по извлечению графа знаний (Knowledge Graph Extraction).\n"
                "Твоя задача - извлекать факты в виде троек (субъект, связь, объект) из текста.\n\n"
                "КРИТИЧЕСКИЕ ПРАВИЛА (ШТРАФ ЗА НАРУШЕНИЕ):\n"
                "1. Узлы (subject и object) должны быть МАКСИМАЛЬНО АТОМАРНЫМИ (обычно 1-3 слова). Это должны быть конкретные сущности или короткие термины, а не куски текста.\n"
                "   ПЛОХО: 'economic analysis of the added value of each development model'\n"
                "   ХОРОШО: 'economic analysis' (и отдельная тройка для 'added value').\n"
                "2. Если в предложении много информации, разбей его на несколько независимых, простых троек.\n"
                "3. АББРЕВИАТУРЫ: ЗАПРЕЩЕНО использовать нерасшифрованные аббревиатуры для компаний или локаций (разворачивай 'NC' в 'New Caledonia', 'KNS' в 'Koniambo Nickel SAS'). ИСКЛЮЧЕНИЕ: Общепринятые химические элементы (Ni, Co, Fe). Для них, чтобы сохранить смысл, используй формат 'Символ (Полное название)', например: 'Ni (Nickel)'.\n"
                "4. ИЗВЛЕКАЙ ТОЛЬКО ЗНАЧИМЫЕ ФАКТЫ: Фокусируйся на знаниях предметной области (металлургия, география, процессы, компании). ИГНОРИРУЙ оглавления (содержание), копирайты, списки литературы и 'воду'. Не создавай 'тройки ради троек', если в них нет фактического смысла. Если текст не содержит полезных фактов (например, это оглавление), просто верни пустой список троек `[]`.\n"
                "5. Используй строго те типы связей и узлов, что разрешены схемой. Если ни одна связь идеально не подходит, используй 'related_to'.\n\n"
                "РАЗРЕШЕННЫЕ ТИПЫ УЗЛОВ (subject_type, object_type):\n"
                "Material, Equipment, Process, Parameter, Metric, Property, Facility, Expert, Regulation, Publication, Location, Organization, Document, Concept\n\n"
                "РАЗРЕШЕННЫЕ ТИПЫ СВЯЗЕЙ (relation):\n"
                "uses_material, operates_at_condition, produces_output, described_in, validated_by, contradicts, located_in, has_property, part_of, managed_by, related_to\n\n"
                "ОБЯЗАТЕЛЬНЫЕ ИНСТРУКЦИИ ПО ФОРМАТУ ВЫВОДА:\n{format_instructions}\n\n"
                "Контекст документа (где находится текст): {meta_context}\n"
                "Текст для анализа:\n{text}\n\n"
                "Извлеки АТОМАРНЫЕ факты из текста строго в указанном формате JSON. Не пиши никакой лишний текст."
            ),
            input_variables=["text", "meta_context"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )
        
        # LCEL Цепочка: Промпт -> Модель -> JSON Парсер
        self.chain = self.prompt | self.llm | self.parser

    async def extract_triples(self, text: str, meta_context: str) -> ExtractionResult:
        try:
            # Асинхронный вызов цепочки (теперь парсер не падает на галлюцинациях)
            result_dict = await self.chain.ainvoke({
                "text": text,
                "meta_context": meta_context
            })
            
            valid_triples = []
            for t in result_dict.get("triples", []):
                rel = t.get("relation")
                subj_type = t.get("subject_type")
                obj_type = t.get("object_type")
                
                # Строгая проверка на соответствие схеме
                if rel in ALLOWED_RELATIONS and subj_type in ALLOWED_NODE_TYPES and obj_type in ALLOWED_NODE_TYPES:
                    valid_triples.append(t)
                else:
                    # Логируем, какую именно тройку мы отбросили (чтобы понимать масштабы галлюцинаций)
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
    
    # -----------------------------------------------------------------
    # Шаг 1: Ingestion & Chunking (Чтение файла)
    # -----------------------------------------------------------------
    import os
    
    # Создаем безопасную папку для картинок (без пробелов и русских букв)
    img_dir = "extracted_images"
    
    # Проверяем расширение файла
    if filepath.lower().endswith(".pdf"):
        import pymupdf4llm
        print(f"Конвертация PDF в Markdown: {filepath}...")
        # ВРЕМЕННО ОТКЛЮЧАЕМ ИЗОБРАЖЕНИЯ (до получения Yandex API ключа)
        markdown_document = pymupdf4llm.to_markdown(
            filepath, 
            write_images=False
        )
    else:
        # Для обычных текстовых файлов (.txt, .md)
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_document = f.read()
            
    # Разделение по заголовкам Markdown
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(markdown_document)
    
    # Дополнительная нарезка (Уменьшили до 1000, чтобы модель не "съедала" детали)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, chunk_overlap=150
    )
    splits = text_splitter.split_documents(md_header_splits)
    
    print(f"Документ успешно разбит на {len(splits)} семантических чанков.\n")
    
    # Инициализация Ollama
    llm = OllamaAPI(model_name="gpt-oss:120b-cloud")
    all_extracted_triples = []
    
    # -----------------------------------------------------------------
    # Шаг 2: LLM Extraction (Асинхронные батчи)
    # -----------------------------------------------------------------
    output_filename = f"{os.path.splitext(filepath)[0]}_extracted.json"
    
    # Очищаем или создаем файл для сохранения прогресса
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump({"triples": []}, f, indent=2, ensure_ascii=False)
        
    # НАСТРОЙКИ ДЛЯ БЕСПЛАТНОГО ТАРИФА (Rate Limits)
    batch_size = 3  # Снизили с 10 до 3 одновременных запросов
    delay_between_batches = 2 # Секунд паузы между батчами
    
    async def process_chunk(chunk, chunk_idx):
        metadata = chunk.metadata
        headers_context = " > ".join([v for k, v in metadata.items() if k.startswith("Header")])
        meta_context = f"Файл: {os.path.basename(filepath)} | Раздел: {headers_context}"
        
        print(f"  [Чанк {chunk_idx}/{len(splits)}] Отправка в модель ({len(chunk.page_content)} симв.)...")
        return await llm.extract_triples(chunk.page_content, meta_context)

    for i in range(0, len(splits), batch_size):
        batch = splits[i:i+batch_size]
        print(f"\n⏳ Обработка батча {i//batch_size + 1}/{(len(splits)-1)//batch_size + 1} (чанки {i+1}-{i+len(batch)})")
        
        tasks = [process_chunk(chunk, i + idx + 1) for idx, chunk in enumerate(batch)]
        
        # Запускаем весь батч параллельно. Игнорируем исключения, чтобы один сбой не убил весь батч.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for res in results:
            if isinstance(res, Exception):
                print(f"❌ Ошибка в чанке: {res}")
            elif isinstance(res, ExtractionResult):
                all_extracted_triples.extend(res.triples)
                
        # Чекпоинт: Сохраняем промежуточный результат после каждого батча
        final_output = {"triples": [t.model_dump() for t in all_extracted_triples]}
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=2, ensure_ascii=False)
        print(f"💾 Чекпоинт сохранен. Всего троек на данный момент: {len(all_extracted_triples)}")
        
        # Пауза для бесплатного API
        if i + batch_size < len(splits):
            print(f"Ожидание {delay_between_batches} сек. перед следующим батчем (Rate Limit)...")
            await asyncio.sleep(delay_between_batches)
        
    print(f"\n✅ Успешно извлечено и сохранено {len(all_extracted_triples)} троек в файл: {output_filename}")

if __name__ == "__main__":
    import sys
    import glob
    import os
    
    # Позволяем передать конкретный файл или папку через аргумент
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.isdir(target):
            test_files = glob.glob(os.path.join(target, "*.pdf"))
        else:
            test_files = [target]
    else:
        # По умолчанию ищем все PDF в текущей папке
        test_files = glob.glob("*.pdf")
        
    if not test_files:
        print("PDF файлы не найдены.")
        
    for test_file in test_files:
        print(f"\n{'='*60}")
        print(f"🚀 СТАРТ ПАЙПЛАЙНА ДЛЯ: {test_file}")
        print(f"{'='*60}\n")
        asyncio.run(run_pipeline(test_file))
