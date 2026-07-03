import os
import json
import asyncio
import pandas as pd
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_community.chat_models import ChatYandexGPT
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# 1. Онтология
# =====================================================================
ALLOWED_NODE_TYPES = [
    "Material", "Equipment", "Process", "Parameter", "Metric", 
    "Property", "Facility", "Expert", "Regulation", "Publication",
    "Geography", "Document", "Concept", "Product"
]

ALLOWED_RELATIONS = [
    "uses_material", "operates_at_condition", "produces_output", 
    "described_in", "validated_by", "contradicts",
    "located_in", "has_property", "part_of", "managed_by", "related_to", "can_substitute"
]

# =====================================================================
# 2. Pydantic схемы для LLM
# =====================================================================
class MappingRule(BaseModel):
    subject_column: str = Field(description="Точное название колонки таблицы для Subject ИЛИ фиксированная строка.")
    subject_type: str = Field(description="Тип Subject из онтологии")
    relation: str = Field(description="Тип связи из онтологии")
    object_column: str = Field(description="Точное название колонки таблицы для Object ИЛИ фиксированная строка.")
    object_type: str = Field(description="Тип Object из онтологии")
    properties_mapping: Dict[str, str] = Field(description="Словарь свойств. Ключ - имя свойства (year, description, practice_origin). Значение - точное название колонки ИЛИ фиксированная строка.")

class ExcelSchemaMapping(BaseModel):
    rules: List[MappingRule] = Field(description="Список правил извлечения. Каждое правило создаст одну тройку из одной строки.")

# =====================================================================
# 3. Агент Схемы
# =====================================================================
class ExcelSmartMapper:
    def __init__(self):
        folder_id = os.environ.get('YC_FOLDER_ID', '')
        self.llm = ChatYandexGPT(
            model_uri=f"gpt://{folder_id}/yandexgpt/latest",
            temperature=0,
            model_kwargs={"format": "json"}
        )
        self.parser = JsonOutputParser(pydantic_object=ExcelSchemaMapping)
        
        self.prompt = PromptTemplate(
            template=(
                "Ты - Data Engineer эксперт по графам знаний. Я дам тебе метаданные таблицы Excel (имя, колонки, примеры первых строк).\n"
                "Твоя задача - написать ПРАВИЛА (схему), по которым скрипт будет автоматически конвертировать КАЖДУЮ СТРОКУ таблицы в факты (тройки).\n\n"
                "ОНТОЛОГИЯ УЗЛОВ: {node_types}\n"
                "ОНТОЛОГИЯ СВЯЗЕЙ: {relations}\n\n"
                "ИНСТРУКЦИЯ:\n"
                "1. Если колонка содержит количественную метрику (например 'Добыча 2020', 'Выручка'), создай правило, где subject - это название компании/материала, relation - 'has_property', object - название колонки или фиксированная строка (например 'Добыча'), а само значение ячейки должно попадать в свойство 'value'.\n"
                "2. Если ты используешь колонку из таблицы, пиши её ТОЧНОЕ название.\n"
                "3. Если в таблице нет нужной колонки (например для года), ты можешь написать фиксированную строку (например '2020').\n"
                "4. В `properties_mapping` ОБЯЗАТЕЛЬНО добавь ключ 'description' с фиксированной строкой, объясняющей суть связи (например 'Статистика по добыче из таблицы').\n"
                "5. В `properties_mapping` ОБЯЗАТЕЛЬНО добавь ключ 'confidence' со значением '1.0' (так как данные из таблицы достоверны на 100%).\n"
                "6. В `properties_mapping` ОБЯЗАТЕЛЬНО добавь ключ 'value', если object_column указывает на колонку с числами.\n\n"
                "МЕТАДАННЫЕ ТАБЛИЦЫ:\n"
                "Файл: {filename}\n"
                "Лист: {sheetname}\n"
                "Колонки: {columns}\n"
                "Первые 3 строки (в JSON формате): {head_rows}\n\n"
                "Формат вывода:\n{format_instructions}\n\n"
                "Верни ТОЛЬКО валидный JSON со схемой маппинга."
            ),
            input_variables=["filename", "sheetname", "columns", "head_rows", "node_types", "relations"],
            partial_variables={"format_instructions": self.parser.get_format_instructions()},
        )
        self.chain = self.prompt | self.llm | self.parser

    async def generate_schema(self, filename: str, sheetname: str, df: pd.DataFrame) -> List[MappingRule]:
        columns = df.columns.tolist()
        head_rows = df.head(3).to_dict(orient="records")
        
        print(f"🤖 Запрашиваю схему у LLM для листа '{sheetname}'...")
        try:
            result = await self.chain.ainvoke({
                "filename": filename,
                "sheetname": sheetname,
                "columns": json.dumps(columns, ensure_ascii=False),
                "head_rows": json.dumps(head_rows, ensure_ascii=False),
                "node_types": ", ".join(ALLOWED_NODE_TYPES),
                "relations": ", ".join(ALLOWED_RELATIONS)
            })
            
            rules = result.get("rules", [])
            print(f"✅ LLM вернула {len(rules)} правил(а) маппинга.")
            return rules
        except Exception as e:
            print(f"❌ Ошибка генерации схемы: {e}")
            return []

    def apply_schema(self, df: pd.DataFrame, rules: List[dict]) -> List[dict]:
        """Локальный сверхбыстрый генератор"""
        triples = []
        columns_set = set(df.columns)
        
        if rules and hasattr(rules[0], 'model_dump'):
            rules = [r.model_dump() for r in rules]
        elif rules and hasattr(rules[0], 'dict'):
             rules = [r.dict() for r in rules]
             
        print(f"⚡ Локальная генерация {len(df)} строк по {len(rules)} правилам...")
        
        for index, row in df.iterrows():
            for rule in rules:
                try:
                    subj_col = rule.get("subject_column", "")
                    subject = str(row[subj_col]) if subj_col in columns_set else subj_col
                    
                    obj_col = rule.get("object_column", "")
                    obj = str(row[obj_col]) if obj_col in columns_set else obj_col
                    
                    if pd.isna(row.get(subj_col, None)) or subject.lower() == "nan" or not subject:
                        continue
                    if pd.isna(row.get(obj_col, None)) or obj.lower() == "nan" or not obj:
                        continue
                        
                    props_mapping = rule.get("properties_mapping", {})
                    properties = {}
                    
                    for k, v in props_mapping.items():
                        properties[k] = str(row[v]) if v in columns_set else v
                        if properties[k].lower() == "nan":
                            properties[k] = ""
                            
                    subj_type = rule.get("subject_type", "Concept")
                    if subj_type not in ALLOWED_NODE_TYPES: subj_type = "Concept"
                    obj_type = rule.get("object_type", "Concept")
                    if obj_type not in ALLOWED_NODE_TYPES: obj_type = "Concept"
                    rel = rule.get("relation", "related_to")
                    if rel not in ALLOWED_RELATIONS: rel = "related_to"

                    triples.append({
                        "subject": subject.strip(),
                        "subject_type": subj_type,
                        "relation": rel,
                        "object": obj.strip(),
                        "object_type": obj_type,
                        "properties": properties
                    })
                except Exception as e:
                    continue
                    
        return triples

async def process_excel_file(filepath: str, output_dir: str = "outputs"):
    print(f"\n{'='*60}\n📊 АНАЛИЗ EXCEL: {filepath}\n{'='*60}")
    mapper = ExcelSmartMapper()
    all_triples = []
    
    try:
        xls = pd.ExcelFile(filepath)
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            if df.empty or len(df.columns) < 2:
                print(f"⚠️ Лист '{sheet_name}' пуст или имеет менее 2 колонок. Пропуск.")
                continue
                
            rules = await mapper.generate_schema(os.path.basename(filepath), sheet_name, df)
            if rules:
                sheet_triples = mapper.apply_schema(df, rules)
                all_triples.extend(sheet_triples)
                print(f"✨ Лист '{sheet_name}': сгенерировано {len(sheet_triples)} фактов.")
                
    except Exception as e:
        print(f"❌ Ошибка обработки Excel файла {filepath}: {e}")
        return
        
    if all_triples:
        file_metadata = {
            "source_file": os.path.basename(filepath),
            "literature_type": "Excel Table"
        }
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.basename(filepath)
        output_filename = os.path.join(output_dir, f"{os.path.splitext(base_name)[0]}_yandex_graph.json")
        
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump({"document_metadata": file_metadata, "triples": all_triples}, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Excel Готово! Извлечено {len(all_triples)} чистых фактов в файл {output_filename}.")
    else:
        print("⚠️ Не удалось извлечь ни одного факта из Excel.")

if __name__ == "__main__":
    import sys
    import glob
    
    if len(sys.argv) > 1:
        target = sys.argv[1]
        test_files = glob.glob(os.path.join(target, "**", "*.xlsx"), recursive=True) if os.path.isdir(target) else [target]
    else:
        test_files = glob.glob("**/*.xlsx", recursive=True)
        
    for f in test_files:
        asyncio.run(process_excel_file(f, "outputs"))
