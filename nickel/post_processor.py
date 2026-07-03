import json
import os
import sys
import asyncio
from pydantic import BaseModel, Field
from typing import Dict, List
from dotenv import load_dotenv

# Математические библиотеки для векторов
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_distances

# Загрузка переменных окружения
load_dotenv()

# Langchain Yandex ищет ключи с префиксом YC_
if os.getenv("YANDEX_API_KEY"):
    os.environ["YC_API_KEY"] = os.getenv("YANDEX_API_KEY").strip('"\'')
if os.getenv("YANDEX_FOLDER_ID"):
    os.environ["YC_FOLDER_ID"] = os.getenv("YANDEX_FOLDER_ID").strip('"\'')

from langchain_community.embeddings import HuggingFaceEmbeddings
import numpy as np
from sklearn.cluster import AgglomerativeClustering

async def global_entity_resolution(unique_entities: List[str]) -> Dict[str, str]:
    if not unique_entities:
        return {}
        
    print(f"\n--- ВЕКТОРНЫЙ ENTITY RESOLUTION ---")
    print(f"1. Локальная векторизация {len(unique_entities)} узлов через BAAI/bge-m3...")
    
    # Инициализация локальной модели (скачается при первом запуске)
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    
    # Получаем векторы мгновенно (без лимитов API)
    try:
        vectors = embeddings.embed_documents(unique_entities)
    except Exception as e:
        print(f"Ошибка локальной векторизации: {e}")
        return {term: term for term in unique_entities}
        
    print(f"2. Кластеризация (AgglomerativeClustering, Cosine Distance <= 0.05)...")
    # Преобразуем в numpy array
    X = np.array(vectors)
    
    # Кластеризация
    # distance_threshold=0.05 означает cosine similarity >= 0.95
    clustering = AgglomerativeClustering(
        n_clusters=None, 
        metric='cosine', 
        linkage='average',
        distance_threshold=0.05 
    )
    labels = clustering.fit_predict(X)
    
    # Группируем слова по кластерам
    clusters = {}
    for term, label in zip(unique_entities, labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(term)
        
    print(f"Сформировано {len(clusters)} кластеров.")
    
    # Разрешение кластеров (Без LLM, чисто алгоритмически)
    mapping = {}
    
    print(f"3. Разрешение кластеров (выбор самого короткого названия)...")
    for label, terms in clusters.items():
        if len(terms) == 1:
            mapping[terms[0]] = terms[0]
        else:
            print(f"  > Слияние кластера: {terms}")
            # Эвристика: берем самое короткое слово как каноничное (например "Никель" вместо "Сплав Никель")
            canonical = sorted(terms, key=len)[0]
            print(f"    [Каноничное имя]: {canonical}")
            for term in terms:
                mapping[term] = canonical
            
    return mapping

async def process_global_graph(filepaths: List[str], output_dir: str = "outputs"):
    print(f"\n{'='*60}\nЗапуск Этапа 3: ГЛОБАЛЬНОЕ СЛИЯНИЕ ({len(filepaths)} файлов)\n{'='*60}")
    
    all_triples = []
    quarantine = []
    
    # 1. Сбор всех троек со всех файлов
    for filepath in filepaths:
        if not os.path.exists(filepath):
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            triples = data.get("triples", [])
            all_triples.extend(triples)
            
    if not all_triples:
        print("Нет троек для обработки.")
        return
        
    print(f"Всего собрано {len(all_triples)} сырых троек.")
    
    # 2. Сбор уникальных узлов
    unique_entities = set()
    
    for t in all_triples:
        subj = str(t.get("subject", "")).strip()
        obj = str(t.get("object", "")).strip()
        
        # Эвристики галлюцинаций LLM
        if len(subj) > 100 or len(obj) > 100:
            quarantine.append({"triple": t, "reason": "Узел слишком длинный (>100 символов)"})
            continue
            
        if len(subj) > 0: unique_entities.add(subj)
        if len(obj) > 0: unique_entities.add(obj)
        
    # 3. Векторный Entity Resolution
    mapping = await global_entity_resolution(list(unique_entities))
    
    # 4. Применение маппинга и дедупликация на глобальном уровне
    cleaned_triples = []
    seen = set()
    
    for t in all_triples:
        raw_subj = str(t.get("subject", "")).strip()
        raw_obj = str(t.get("object", "")).strip()
        
        if len(raw_subj) > 100 or len(raw_obj) > 100:
            continue
            
        subject_canon = mapping.get(raw_subj, raw_subj)
        object_canon = mapping.get(raw_obj, raw_obj)
        
        subject_type = t.get("subject_type", "Unknown")
        relation = t.get("relation", "related_to")
        object_type = t.get("object_type", "Unknown")
        properties = t.get("properties", {}) 
        
        prop_str = json.dumps(properties, sort_keys=True)
        triple_key = f"{subject_canon.lower()}|{relation}|{object_canon.lower()}|{prop_str}"
        
        if triple_key not in seen:
            seen.add(triple_key)
            cleaned_triples.append({
                "subject": subject_canon,
                "subject_type": subject_type,
                "relation": relation,
                "object": object_canon,
                "object_type": object_type,
                "properties": properties
            })
            
    # Сохраняем ГЛОБАЛЬНЫЙ результат
    os.makedirs(output_dir, exist_ok=True)
    clean_out = os.path.join(output_dir, "global_cleaned_graph.json")
    with open(clean_out, "w", encoding="utf-8") as f:
        json.dump({"triples": cleaned_triples}, f, indent=2, ensure_ascii=False)
        
    print(f"\n=== Итоги Глобального Этапа 3 ===")
    print(f"Всего троек на входе: {len(all_triples)}")
    print(f"Уникальных узлов: {len(unique_entities)}")
    print(f"✅ Осталось чистых глобальных фактов (дедуплицированных): {len(cleaned_triples)}")
    print(f"💾 Результат сохранен в: {clean_out}")

if __name__ == "__main__":
    import argparse
    import glob
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=str, default="outputs", help="Папка с *_yandex_graph.json файлами")
    parser.add_argument("--out", type=str, default="outputs", help="Куда сохранить global_cleaned_graph.json")
    args = parser.parse_args()
    
    test_files = glob.glob(os.path.join(args.dir, "*_yandex_graph.json"))
        
    if not test_files:
        print(f"Файлы *_yandex_graph.json не найдены в папке {args.dir}")
    else:
        asyncio.run(process_global_graph(test_files, args.out))
