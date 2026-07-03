import json
import os
import sys
import asyncio
from pydantic import BaseModel, Field
from typing import Dict, List
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

class EntityMapping(BaseModel):
    mapping: Dict[str, str] = Field(description="Словарь, где ключ - это исходное имя, а значение - каноничное имя на русском языке.")

async def resolve_entities(unique_entities: List[str], model_name: str = "gpt-oss:120b-cloud") -> Dict[str, str]:
    """Отправляет список уникальных терминов в LLM для группировки синонимов и приведения к каноничному виду."""
    if not unique_entities:
        return {}
        
    print(f"Отправка {len(unique_entities)} уникальных сущностей в LLM для слияния синонимов...")
    
    llm = ChatOllama(model=model_name, base_url="http://localhost:11434", format="json", temperature=0)
    parser = JsonOutputParser(pydantic_object=EntityMapping)
    
    prompt = PromptTemplate(
        template=(
            "Ты эксперт-металлург и лингвист. Ниже приведен список извлеченных сущностей из документов.\n"
            "Твоя задача - найти среди них синонимы, аббревиатуры (например, 'NC' и 'New Caledonia') и переводы (английский и русский), "
            "и свести их к единому КАНОНИЧНОМУ названию строго на РУССКОМ языке (если это возможно).\n\n"
            "Правила:\n"
            "1. Верни JSON-объект 'mapping', где КЛЮЧ — это оригинальная строка из списка, а ЗНАЧЕНИЕ — каноничное русское название.\n"
            "2. В 'mapping' должны присутствовать ВСЕ переданные элементы.\n"
            "3. Географические и корпоративные аббревиатуры (NC, KNS) расшифровывай в полные названия (Новая Каледония, Koniambo Nickel SAS).\n"
            "4. ХИМИЧЕСКИЕ ЭЛЕМЕНТЫ: оставляй символ, но добавляй расшифровку в скобках для сохранения векторного смысла. Формат: 'Символ (Название)', например: 'Ni (Никель)', 'Co (Кобальт)'.\n"
            "5. Исправляй опечатки.\n\n"
            "Формат вывода:\n{format_instructions}\n\n"
            "Список сущностей:\n{entities}\n"
        ),
        input_variables=["entities"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    chain = prompt | llm | parser
    
    try:
        # Для очень больших списков в проде нужно делать батчинг (Вариант 4 из Плана).
        # Для MVP отправляем все сразу.
        entities_str = "\n".join([f"- {e}" for e in unique_entities])
        result = await chain.ainvoke({"entities": entities_str})
        return result.get("mapping", {})
    except Exception as e:
        print(f"Ошибка LLM Entity Resolution: {e}")
        # Fallback: возвращаем 1:1 маппинг
        return {e: e for e in unique_entities}

async def clean_and_process(filepath: str):
    print(f"Запуск Этапа 3 (Очистка и Entity Resolution) для файла: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"Ошибка: Файл {filepath} не найден.")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    triples = data.get("triples", [])
    
    # 1. Сбор уникальных узлов
    unique_entities = set()
    quarantine = []
    
    for t in triples:
        subj = str(t.get("subject", "")).strip()
        obj = str(t.get("object", "")).strip()
        
        # Эвристики галлюцинаций LLM (Фильтрация мусора ДО слияния)
        if len(subj) > 80 or len(obj) > 80:
            quarantine.append({"triple": t, "reason": "Too long (hallucination?)"})
            continue
            
        if len(subj) > 0: unique_entities.add(subj)
        if len(obj) > 0: unique_entities.add(obj)
        
    # 2. Вызов LLM для слияния
    mapping = await resolve_entities(list(unique_entities))
    
    print("\n--- Результат слияния (Словарь синонимов) ---")
    for k, v in mapping.items():
        if k.lower() != v.lower():
            print(f"Слияние: '{k}' -> '{v}'")
            
    # 3. Применение маппинга и дедупликация
    cleaned_triples = []
    seen = set()
    
    for t in triples:
        try:
            raw_subj = str(t["subject"]).strip()
            raw_obj = str(t["object"]).strip()
            
            # Пропускаем отбракованные
            if len(raw_subj) > 80 or len(raw_obj) > 80:
                continue
                
            subject_canon = mapping.get(raw_subj, raw_subj)
            object_canon = mapping.get(raw_obj, raw_obj)
            
            subject_type = t["subject_type"]
            relation = t["relation"]
            object_type = t["object_type"]
            
            # Дедупликация (по нижнему регистру каноничных имен)
            triple_key = f"{subject_canon.lower()}|{subject_type}|{relation}|{object_canon.lower()}|{object_type}"
            
            if triple_key not in seen:
                seen.add(triple_key)
                cleaned_triples.append({
                    "subject": subject_canon,
                    "subject_type": subject_type,
                    "relation": relation,
                    "object": object_canon,
                    "object_type": object_type
                })
        except KeyError as e:
            quarantine.append({"triple": t, "reason": f"Missing key {e}"})
            
    # Сохраняем результаты
    base_name = os.path.splitext(filepath)[0].replace("_extracted", "")
    
    clean_out = f"{base_name}_cleaned_graph.json"
    with open(clean_out, "w", encoding="utf-8") as f:
        json.dump({"triples": cleaned_triples}, f, indent=2, ensure_ascii=False)
        
    quarantine_out = f"{base_name}_quarantine.json"
    with open(quarantine_out, "w", encoding="utf-8") as f:
        json.dump({"quarantined": quarantine}, f, indent=2, ensure_ascii=False)
        
    print(f"\n=== Итоги Этапа 3 ===")
    print(f"Всего троек на входе: {len(triples)}")
    print(f"Уникальных узлов обработано LLM: {len(unique_entities)}")
    print(f"✅ Осталось чистых (дедуплицированных): {len(cleaned_triples)} -> сохранено в {clean_out}")
    print(f"⚠️ Отправлено в карантин (мусор): {len(quarantine)} -> сохранено в {quarantine_out}")

if __name__ == "__main__":
    import glob
    
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.isdir(target):
            test_files = glob.glob(os.path.join(target, "*_extracted.json"))
        else:
            test_files = [target]
    else:
        test_files = glob.glob("*_extracted.json")
        
    if not test_files:
        print("Файлы *_extracted.json не найдены.")
        
    for test_file in test_files:
        print(f"\n{'='*60}")
        print(f"🧹 СТАРТ ПОСТ-ПРОЦЕССИНГА ДЛЯ: {test_file}")
        print(f"{'='*60}\n")
        asyncio.run(clean_and_process(test_file))
