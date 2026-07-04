import os
import glob
import json
import asyncio
import re
from typing import List, Optional
from dotenv import load_dotenv
from docx import Document
from services.excel_mapper import process_excel_file

# Загрузка переменных окружения из .env
load_dotenv()

# Langchain Yandex ищет ключи с префиксом YC_
if os.getenv("YANDEX_API_KEY"):
    os.environ["YC_API_KEY"] = os.getenv("YANDEX_API_KEY").strip('"\'')
if os.getenv("YANDEX_FOLDER_ID"):
    os.environ["YC_FOLDER_ID"] = os.getenv("YANDEX_FOLDER_ID").strip('"\'')

from langchain_community.chat_models import ChatYandexGPT
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

import pymupdf4llm

# =====================================================================
# 1. Онтология (Rich Property Graph)
# =====================================================================
ALLOWED_NODE_TYPES = [
    "Material", "Equipment", "Process", "Parameter", "Metric", 
    "Property", "Facility", "Expert", "Document", "Product"
]

ALLOWED_RELATIONS = [
    "uses_material", "operates_at_condition", "produces_output", 
    "described_in", "validated_by", "contradicts",
    "has_property", "part_of", "can_substitute"
]

NodeType = str
RelationType = str

class Triple(BaseModel):
    subject: str = Field(description="Имя субъекта (исходного узла)")
    subject_type: NodeType = Field(description="Тип субъекта из онтологии")
    relation: RelationType = Field(description="Тип связи из онтологии")
    object: str = Field(description="Имя объекта (целевого узла)")
    object_type: NodeType = Field(description="Тип объекта из онтологии")
    properties: dict = Field(default_factory=dict, description="Словарь свойств (условия, концентрации, температуры, параметры)")

class ExtractionResult(BaseModel):
    triples: List[Triple] = Field(description="Список извлеченных троек (фактов)")

# =====================================================================
# 2. Роутер и Пре-фильтр
# =====================================================================

def detect_language_type(text: str) -> str:
    """Определяет тип литературы (RU или EN) по наличию кириллицы."""
    if re.search(r'[А-Яа-я]', text[:1000]):
        return "RU"
    return "EN"

def should_process_chunk(text: str) -> bool:
    """Эвристика для отбрасывания оглавлений и списков литературы."""
    lower_text = text.lower()
    if "оглавление" in lower_text[:100] or "table of contents" in lower_text[:100]:
        return False
    if "список литературы" in lower_text[:100] or "references" in lower_text[:100]:
        return False
    if len(text.strip()) < 50:
        return False
    return True

# =====================================================================
# 3. Yandex API Экстрактор (С RPG Промптом)
# =====================================================================

class YandexExtractor:
    def __init__(self):
        self.llm = ChatYandexGPT(
            model_uri=f"gpt://{os.environ.get('YC_FOLDER_ID', '')}/yandexgpt/latest",
            temperature=0,
            model_kwargs={"format": "json"}
        )
        self.parser = JsonOutputParser(pydantic_object=ExtractionResult)
        
        self.prompt = PromptTemplate(
            template=(
                "Ты - эксперт по извлечению графа знаний (Knowledge Graph Extraction). Твоя задача извлекать структурированные факты (тройки со свойствами) из текста.\n\n"
                "КРИТИЧЕСКИЕ ПРАВИЛА (КАК ПРАВИЛЬНО СТРОИТЬ ГРАФ И ИЗБЕГАТЬ 'ВОДЫ'):\n"
                "1. НЕ СОЗДАВАЙ 'ТРОЙКИ РАДИ ТРОЕК'. Извлекай только конкретные факты (инженерия, химия, металлургия, а также важная статистика компаний и история).\n"
                "2. БЕЗЖАЛОСТНО УДАЛЯЙ 'ВОДУ': Если факт слишком общий и не несет конкретики (например 'Оборудование важно для процесса') — ЭТО МУСОР, ВОЗВРАЩАЙ `[]`.\n"
                "3. АДМИНИСТРАТИВНЫЙ МУСОР: Игнорируй бюрократию, законы, процедуры авторизации ('Authorization procedure'), финансовые гарантии и общие исследования, если в них нет физики/химии/металлургии.\n"
                "4. АДЕКВАТНОСТЬ И ЛОГИКА: Связи должны иметь строгий физический или экономический смысл. Не связывай несопоставимые вещи.\n"
                "5. ЯЗЫК ОРИГИНАЛА: ОБЯЗАТЕЛЬНО сохраняй оригинальный язык текста для названий узлов (subject/object) и значений свойств.\n"
                "6. Узлы (subject/object) должны быть КОРОТКИМИ (1-3 слова). Годы (2009, 2012) и числа НЕ МОГУТ БЫТЬ УЗЛАМИ!\n"
                "7. СТАТИСТИКА И ПОКАЗАТЕЛИ: Строй связь 'has_property' от МАТЕРИАЛА, ПРОЦЕССА или ПРЕДПРИЯТИЯ к МЕТРИКЕ (например, 'Palladium' -> 'has_property' -> 'Demand'). ЗАПРЕЩЕНО связывать Метрику с Метрикой.\n"
                "8. СВОЙСТВА (properties): Числа, концентрации, температуры, ГОДЫ сохраняй ТОЛЬКО внутри properties. НЕ ПИШИ в properties авторов или название журнала, это мусор!\n"
                "9. ОПИСАНИЕ СВЯЗИ: В словаре properties ОБЯЗАТЕЛЬНО должно быть поле `description` (1 краткое предложение, объясняющее суть этой связи в контексте текста).\n"
                "10. ИСТОЧНИК ПРАКТИКИ: Если из текста понятно, к какой практике относится факт (русская, международная, китайская), укажи это в поле `practice_origin` внутри properties.\n"
                "11. АБСОЛЮТНОЕ ВРЕМЯ (ГОДЫ): Никогда не пиши 'прошлый год' или 'текущий год'. Всегда высчитывай и пиши точный год (например, 2012) из контекста.\n\n"
                "ЗНАЧЕНИЯ СВЯЗЕЙ (ИСПОЛЬЗУЙ ПРАВИЛЬНО!):\n"
                "- contradicts: ИСПОЛЬЗУЙ ТОЛЬКО если два научных факта или цифры прямо противоречат друг другу (научный спор).\n"
                "- can_substitute: Используй, если один материал/технология может заменить другой (например, Палладий заменяет Платину).\n\n"
                "РАЗРЕШЕННЫЕ ТИПЫ УЗЛОВ (Концепции и законы запрещены, только конкретика!):\n"
                "Material, Equipment, Process, Parameter, Metric, Property, Facility, Expert, Document, Product\n"
                "РАЗРЕШЕННЫЕ ТИПЫ СВЯЗЕЙ (related_to ЗАПРЕЩЕНО, связи должны быть физическими/строгими!):\n"
                "uses_material, operates_at_condition, produces_output, described_in, validated_by, contradicts, has_property, part_of, can_substitute\n\n"
                "--- ПРИМЕРЫ (Few-Shot) ---\n"
                "Текст: 'The new mining law is a modern regulation tool that supports our industrial strategy.'\n"
                "Твой ответ: {{\"triples\": []}} (Пояснение: это общие слова, маркетинговая 'вода' без параметров, мусор)\n\n"
                "Текст: 'В 2009 году на заводе SLN работало 2369 сотрудников, а добыча составила 60000T.'\n"
                "Твой ответ: {{\"triples\": [\n"
                "  {{\"subject\": \"SLN\", \"subject_type\": \"Facility\", \"relation\": \"has_property\", \"object\": \"Сотрудники\", \"object_type\": \"Metric\", \"properties\": {{\"year\": \"2009\", \"value\": \"2369\"}}}},\n"
                "  {{\"subject\": \"SLN\", \"subject_type\": \"Facility\", \"relation\": \"has_property\", \"object\": \"Добыча\", \"object_type\": \"Metric\", \"properties\": {{\"year\": \"2009\", \"value\": \"60000T\"}}}}\n"
                "]}}\n\n"
                "Текст: 'В китайской практике для выщелачивания руды применяют серную кислоту при температуре 150C.'\n"
                "Твой ответ: {{\"triples\": [\n"
                "  {{\"subject\": \"выщелачивание руды\", \"subject_type\": \"Process\", \"relation\": \"uses_material\", \"object\": \"серная кислота\", \"object_type\": \"Material\", \"properties\": {{\"temperature\": \"150C\", \"description\": \"В китайской практике для выщелачивания применяют серную кислоту\", \"practice_origin\": \"китайская\", \"confidence\": \"0.95\"}}}}\n"
                "]}}\n\n"
                "ОБЯЗАТЕЛЬНЫЕ ИНСТРУКЦИИ ПО СВОЙСТВАМ (properties):\n"
                "- ОБЯЗАТЕЛЬНО добавь `description` (1 краткое предложение, объясняющее суть связи в контексте текста).\n"
                "- ОБЯЗАТЕЛЬНО добавь `practice_origin` (русская, международная, китайская и т.д., если применимо).\n"
                "- ОБЯЗАТЕЛЬНО добавь `confidence` (вещественное число от 0.1 до 1.0, где 1.0 - факт прямо и явно утверждается в тексте, 0.5 - подразумевается косвенно).\n"
                "- АБСОЛЮТНОЕ ВРЕМЯ: Никогда не пиши 'прошлый год' или 'текущий год'. Высчитывай точный год из контекста (например 'year': '2012').\n\n"
                "Формат вывода: ТОЛЬКО валидный JSON.\n"
                "ОБЯЗАТЕЛЬНЫЕ ИНСТРУКЦИИ ПО ФОРМАТУ ВЫВОДА:\n{format_instructions}\n\n"
                "Контекст документа: {meta_context}\n"
                "Текст:\n{text}\n\n"
                "Извлеки факты строго в формате JSON."
            ),
            input_variables=["text", "meta_context"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )
        self.chain = self.prompt | self.llm | self.parser

    async def extract_triples(self, text: str, meta_context: str) -> List[dict]:
        try:
            result_dict = await self.chain.ainvoke({
                "text": text,
                "meta_context": meta_context
            })
            
            valid_triples = []
            for t in result_dict.get("triples", []):
                rel = t.get("relation")
                subj_type = t.get("subject_type")
                obj_type = t.get("object_type")
                
                if rel in ALLOWED_RELATIONS and subj_type in ALLOWED_NODE_TYPES and obj_type in ALLOWED_NODE_TYPES:
                    valid_triples.append(t)
                else:
                    pass
            return valid_triples
        except Exception as e:
            print(f"❌ Ошибка парсинга JSON от Yandex: {e}")
            return []

# =====================================================================
# 4. Оркестратор
# =====================================================================

async def process_file(filepath: str, extractor: YandexExtractor, output_dir: str):
    print(f"\n{'='*60}\n🚀 АНАЛИЗ ФАЙЛА: {filepath}\n{'='*60}")
    
    if filepath.lower().endswith(".pdf"):
        print("Конвертация PDF в Markdown...")
        markdown_text = pymupdf4llm.to_markdown(filepath, write_images=False)
    elif filepath.lower().endswith(".docx"):
        print("Чтение DOCX...")
        doc = Document(filepath)
        markdown_text = "\n".join([para.text for para in doc.paragraphs])
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_text = f.read()
            
    lang_type = detect_language_type(markdown_text)
    file_metadata = {
        "source_file": os.path.basename(filepath),
        "literature_type": lang_type
    }
    print(f"📄 Метаданные файла: Литература [{lang_type}]")
    
    headers_to_split_on = [("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")]
    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_splits = md_splitter.split_text(markdown_text)
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=150)
    splits = text_splitter.split_documents(md_splits)
    
    print(f"✂️ Документ разбит на {len(splits)} чанков.")
    
    all_triples = []
    
    base_name = os.path.basename(filepath)
    output_filename = os.path.join(output_dir, f"{os.path.splitext(base_name)[0]}_yandex_graph.json")
    
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump({"document_metadata": file_metadata, "triples": []}, f, indent=2, ensure_ascii=False)
        
    batch_size = 8  # Yandex RPS limit
    
    async def process_chunk(chunk, idx):
        if not should_process_chunk(chunk.page_content):
            return []
            
        context = " > ".join([v for k, v in chunk.metadata.items() if k.startswith("Header")])
        meta_context = f"Файл: {os.path.basename(filepath)} | Язык: {lang_type} | Раздел: {context}"
        
        await asyncio.sleep(idx * 0.1)
        return await extractor.extract_triples(chunk.page_content, meta_context)

    for i in range(0, len(splits), batch_size):
        batch = splits[i:i+batch_size]
        print(f"⏳ Отправка батча {i//batch_size + 1}/{(len(splits)-1)//batch_size + 1} в YandexGPT (по {batch_size} чанков)...")
        
        tasks = [process_chunk(chunk, i + idx + 1) for idx, chunk in enumerate(batch)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for res in results:
            if isinstance(res, list):
                all_triples.extend(res)
            elif isinstance(res, Exception):
                print(f"❌ Ошибка в батче: {res}")
                
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump({"document_metadata": file_metadata, "triples": all_triples}, f, indent=2, ensure_ascii=False)
            
    print(f"✅ Готово! Извлечено {len(all_triples)} чистых фактов.")

async def main(input_dir: str, output_dir: str):
    if not os.path.exists(input_dir):
        print(f"Папка {input_dir} не найдена.")
        return
        
    os.makedirs(output_dir, exist_ok=True)
        
    print(f"Инициализация Yandex Studio Оркестратора для папки: {input_dir}")
    
    pdf_files = glob.glob(os.path.join(input_dir, "**", "*.pdf"), recursive=True)
    docx_files = glob.glob(os.path.join(input_dir, "**", "*.docx"), recursive=True)
    xlsx_files = glob.glob(os.path.join(input_dir, "**", "*.xlsx"), recursive=True)
    
    doc_files = pdf_files + docx_files
    
    print(f"Найдено текстовых файлов для анализа: {len(doc_files)}")
    print(f"Найдено таблиц Excel для умного анализа: {len(xlsx_files)}")
    
    extractor = YandexExtractor()
    
    # 1. Текстовые документы (PDF, DOCX)
    for f in doc_files:
        await process_file(f, extractor, output_dir)
        
    # 2. Таблицы (XLSX) - отправляем в Smart Mapper
    for f in xlsx_files:
        await process_excel_file(f, output_dir)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Yandex GraphRAG Orchestrator")
    parser.add_argument("--dir", type=str, default="dirs", help="Папка с документами для анализа")
    parser.add_argument("--out", type=str, default="outputs", help="Папка для сохранения результатов")
    args = parser.parse_args()
    
    asyncio.run(main(args.dir, args.out))
