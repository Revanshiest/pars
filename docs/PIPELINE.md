# Пайплайн обработки документов

Пайплайн извлекает знания из документов, нормализует их через глоссарий, валидирует SHACL и загружает в Neo4j + Qdrant + SQLite.

---

## Поддерживаемые форматы

| Формат | Расширения | Extractor |
|--------|------------|-----------|
| PDF | `.pdf` | Ollama / Yandex |
| Word | `.docx` | Ollama / Yandex |
| Markdown / текст | `.md`, `.txt` | Ollama / Yandex |
| Excel | `.xlsx`, `.xls` | excel_mapper (без LLM) |

---

## Этапы пайплайна

```
route → ingest → extract → document_context → entity_resolution
  → numeric_extract → glossary → validate (SHACL) → rdf → neo4j → qdrant → done
```

| Этап | Описание |
|------|----------|
| **route** | Выбор backend: Excel vs текстовый документ |
| **ingest** | Парсинг PDF/DOCX → markdown, chunking (1000 символов, overlap 150) |
| **extract** | LLM извлекает тройки (subject, relation, object) батчами |
| **document_context** | Тип документа (patent, report, publication…) |
| **entity_resolution** | Слияние дубликатов сущностей |
| **numeric_extract** | Числовые параметры в properties |
| **glossary** | Нормализация терминов по SQLite-глоссарию |
| **validate** | SHACL; при `STRICT_SHACL=true` блокирует Neo4j |
| **rdf** | Экспорт TTL/JSON-LD |
| **neo4j** | Загрузка графа |
| **qdrant** | Индексация чанков и сущностей |

---

## Способ 1: CLI (локально)

**Требования:** Neo4j, Qdrant, Ollama (или Yandex API) запущены; `.env` настроен.

```bash
cd nickel
pip install -r requirements.txt
cp ../.env.example ../.env   # отредактировать при необходимости

# Один файл
python cli.py pipeline path/to/document.pdf

# С выбором экстрактора
python cli.py pipeline report.docx --extractor ollama
python cli.py pipeline report.docx --extractor yandex
python cli.py pipeline report.docx --extractor auto

# Куда писать артеfacts
python cli.py pipeline doc.pdf --output-dir data/outputs
```

Результат печатается в stdout (JSON): `triples_count`, `json_path`, `rdf_path`, `neo4j`, `qdrant`.

**Legacy (только LLM, без Neo4j/Qdrant):**

```bash
python cli.py mvp document.pdf
```

---

## Способ 2: API — один файл

```bash
# 1. Получить API-key (первый admin через /admin/ или setup)
curl -X POST http://localhost:8000/api/v1/auth/setup \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@org.local","name":"Admin"}'

# 2. Загрузить файл (фоновая задача)
curl -X POST "http://localhost:8000/api/v1/documents/upload?extractor=auto" \
  -H "X-API-Key: YOUR_KEY" \
  -F "file=@report.pdf"
# → {"id":"job-uuid","status":"pending",...}

# 3. Следить за прогрессом
curl http://localhost:8000/api/v1/jobs/JOB_ID -H "X-API-Key: YOUR_KEY"

# 4. Логи задачи
curl http://localhost:8000/api/v1/jobs/JOB_ID/logs -H "X-API-Key: YOUR_KEY"
```

---

## Способ 3: API — папка (batch)

Обработка всех файлов в каталоге на **сервере** (Docker volume `api_data` → `/app/data/inbox`).

```bash
# Положить PDF в data/inbox/ (локально или в volume контейнера)
mkdir -p data/inbox
cp reports/*.pdf data/inbox/

# Запустить batch
curl -X POST http://localhost:8000/api/v1/documents/ingest-folder \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_path": "data/inbox",
    "extractor": "auto",
    "recursive": false
  }'
```

Разрешённые корни: `INGEST_ROOTS` (по умолчанию `data/inbox`, `data/uploads`).

Дочерние задачи: `GET /api/v1/jobs/{batch_id}/children`.

---

## Способ 4: Web UI

1. Откройте http://localhost:8080
2. Войдите по API-key
3. **Обработка** → укажите путь `data/inbox` или загрузите файлы drag-and-drop
4. Список активных задач и логи — видны всем пользователям с правом `read`

---

## Docker: полный стек + пайплайн

```bash
cp .env.example .env
docker compose up -d --build

# Файлы для ingest (volume api_data)
docker cp report.pdf nickel-api:/app/data/inbox/

# Через UI или API (см. выше)
```

**Ollama** на хосте: в `.env` / compose уже `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

---

## Переменные окружения (пайплайн)

| Переменная | Значение | Описание |
|------------|----------|----------|
| `EXTRACTOR_BACKEND` | `auto` / `ollama` / `yandex` | Backend по умолчанию |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API |
| `OLLAMA_MODEL` | `gpt-oss:120b-cloud` | Модель |
| `YANDEX_API_KEY` | — | Yandex GPT (если yandex) |
| `YANDEX_FOLDER_ID` | — | Folder Yandex Cloud |
| `STRICT_SHACL` | `true` | Блок Neo4j при ошибке SHACL |
| `UPLOAD_DIR` | `data/uploads` | Загрузки через API |
| `OUTPUT_DIR` | `data/outputs` | JSON/RDF результаты |
| `INGEST_ROOTS` | `data/inbox,data/uploads` | Корни для batch ingest |

---

## Артефакты

После успешного прогона в `OUTPUT_DIR`:

```
data/outputs/
  {job_id}_{filename}_extracted.json   # тройки + metadata
  {job_id}_{filename}.ttl              # RDF
```

Факты также в SQLite (`PLATFORM_DB` → `verified_facts`) и Neo4j.

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| Ollama connection refused | Запустите Ollama; проверьте `OLLAMA_BASE_URL` |
| Neo4j unavailable | `docker compose ps`; дождитесь healthy neo4j |
| Qdrant unavailable | Порт 6333; semantic search не работает без Qdrant |
| SHACL rejected | Смотрите `result.shacl` в job; ослабьте `STRICT_SHACL=false` для отладки |
| Пустая папка batch | Положите `.pdf/.docx/...` в `data/inbox` |
| Path not allowed | Путь должен быть внутри `INGEST_ROOTS` |
