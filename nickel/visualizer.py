import json
import os
import sys
import glob
import networkx as nx
from pyvis.network import Network

# Настройка цветов для типов узлов
COLOR_MAP = {
    "Material": "#9E9E9E",      # Серый
    "Equipment": "#795548",     # Коричневый
    "Process": "#FF9800",       # Оранжевый
    "Parameter": "#2196F3",     # Синий
    "Metric": "#4CAF50",        # Зеленый
    "Property": "#00BCD4",      # Голубой
    "Facility": "#3F51B5",      # Индиго
    "Expert": "#9C27B0",        # Фиолетовый
    "Document": "#607D8B",      # Сине-серый
    "Product": "#E91E63",       # Розовый
    "Unknown": "#D3D3D3"
}

def generate_html(filepath: str, output_dir: str):
    print(f"Генерация визуализации для {filepath}...")
    
    if not os.path.exists(filepath):
        print(f"Файл {filepath} не найден!")
        return

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    triples = data.get("triples", [])
    if not triples:
        print("В файле нет троек. Визуализировать нечего.")
        return

    # Создаем граф NetworkX
    G = nx.DiGraph()

    for t in triples:
        subj = t.get("subject")
        subj_type = t.get("subject_type", "Unknown")
        rel = t.get("relation")
        obj = t.get("object")
        obj_type = t.get("object_type", "Unknown")
        props = t.get("properties", {})

        if not subj or not obj:
            continue

        # Добавляем узлы
        if subj not in G:
            G.add_node(subj, group=subj_type, color=COLOR_MAP.get(subj_type, COLOR_MAP["Unknown"]), title=f"Type: {subj_type}")
        if obj not in G:
            G.add_node(obj, group=obj_type, color=COLOR_MAP.get(obj_type, COLOR_MAP["Unknown"]), title=f"Type: {obj_type}")

        # Формируем tooltip для связи (показываем свойства при наведении)
        edge_title = f"Relation: {rel}"
        if props:
            edge_title += "\n\n"
            desc = props.pop("description", None)
            origin = props.pop("practice_origin", None)
            
            if desc:
                edge_title += f"Суть: {desc}\n"
            if origin:
                edge_title += f"Практика: {origin}\n"
                
            if props:
                edge_title += "\nПараметры:\n"
                for k, v in props.items():
                    edge_title += f"- {k}: {v}\n"
                    
            # Восстанавливаем свойства обратно, если они нужны дальше (хотя мы их просто выводим)
            if desc: props["description"] = desc
            if origin: props["practice_origin"] = origin

        # Добавляем ребро
        G.add_edge(subj, obj, title=edge_title, label=rel)

    # Инициализация PyVis Network
    net = Network(height="1000px", width="100%", directed=True, bgcolor="#222222", font_color="white")
    
    # Загружаем данные из NetworkX
    net.from_nx(G)

    # Настраиваем физику (алгоритм Barnes Hut отлично подходит для графов знаний)
    net.set_options("""
    var options = {
      "nodes": {
        "shape": "dot",
        "size": 20,
        "font": {
          "size": 14,
          "color": "#ffffff"
        },
        "borderWidth": 2
      },
      "edges": {
        "color": {
          "inherit": true
        },
        "smooth": false,
        "font": {
            "size": 12,
            "color": "#cccccc",
            "align": "middle"
        }
      },
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -30000,
          "centralGravity": 0.3,
          "springLength": 200,
          "springConstant": 0.04,
          "damping": 0.09,
          "avoidOverlap": 0.1
        },
        "minVelocity": 0.75
      }
    }
    """)

    # Сохраняем результат
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.basename(filepath)
    out_file = os.path.join(output_dir, f"{os.path.splitext(base_name)[0]}_visualization.html")
    
    net.save_graph(out_file)
    print(f"✅ Граф успешно сохранен в {out_file}")
    print(f"Откройте {out_file} в любом веб-браузере.")

if __name__ == "__main__":
    import argparse
    import glob
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=str, default="outputs", help="Папка с *_cleaned_graph.json файлами")
    parser.add_argument("--out", type=str, default="outputs", help="Куда сохранить HTML")
    args = parser.parse_args()
    
    test_files = glob.glob(os.path.join(args.dir, "*_cleaned_graph.json"))
        
    if not test_files:
        print(f"Файлы *_cleaned_graph.json не найдены в папке {args.dir}")
    else:
        for f in test_files:
            generate_html(f, args.out)
