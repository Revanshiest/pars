import os
import json
import argparse
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

def inspect_chunks(filepath: str):
    print(f"Инспекция чанков для файла: {filepath}")
    
    if not os.path.exists(filepath):
        print(f"Ошибка: Файл {filepath} не найден.")
        return

    # Шаг 1: Ingestion
    if filepath.lower().endswith(".pdf"):
        import pymupdf4llm
        print(f"Конвертация PDF в Markdown...")
        markdown_document = pymupdf4llm.to_markdown(filepath)
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_document = f.read()
            
    # Шаг 2: Chunking по заголовкам
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    md_header_splits = markdown_splitter.split_text(markdown_document)
    
    # Шаг 3: Дополнительная нарезка длинных секций (fallback)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=50
    )
    splits = text_splitter.split_documents(md_header_splits)
    
    print(f"Файл успешно разбит на {len(splits)} чанков.")
    
    # Шаг 4: Форматирование вывода
    output_data = []
    for i, chunk in enumerate(splits):
        metadata = chunk.metadata
        headers_context = " > ".join([v for k, v in metadata.items() if k.startswith("Header")])
        meta_context = f"Файл: {os.path.basename(filepath)} | Раздел: {headers_context}"
        
        output_data.append({
            "chunk_index": i + 1,
            "meta_context": meta_context,
            "text_length": len(chunk.page_content),
            "content": chunk.page_content
        })
        
    output_filename = f"{os.path.splitext(filepath)[0]}_chunks.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Чанки успешно сохранены для проверки в файл: {output_filename}")

if __name__ == "__main__":
    import sys
    # Позволяем передавать файл через аргумент командной строки
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    else:
        target_file = "Aurelien_Louis_Горная промышленность в Новой Каледонии.pdf"
        
    inspect_chunks(target_file)
