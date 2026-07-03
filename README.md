# Nickel — R&D Knowledge Graph Platform

Платформа извлечения, хранения, верификации и анализа знаний из научно-технической документации (никель, heap leaching, арктические условия).

**Стек:** FastAPI · React · SQLite · Neo4j · Qdrant · Ollama/Yandex GPT · RDF/SHACL · reportlab · Docker

---

## Документация

| Раздел | Файл |
|--------|------|
| **Запуск пайплайна** | [docs/PIPELINE.md](docs/PIPELINE.md) |
| Развёртывание Docker / nginx | [docs/DEPLOY.md](docs/DEPLOY.md) |
| REST API | [docs/API.md](docs/API.md) |
| Индекс документации | [docs/README.md](docs/README.md) |

---

## Быстрый старт (5 минут)

```bash
cp .env.example .env          # JWT_SECRET — мин. 32 символа
docker compose up -d --build  # Neo4j + Qdrant + API + UI + nginx
```

| URL | Назначение |
|-----|------------|
| http://localhost:8080 | **Web UI** (обработка, поиск) |
| http://localhost:8000/docs | Swagger API |
| http://localhost:8080/admin/ | Первый admin + API-key |

**Пайплайн через UI:** положите PDF в `data/inbox/` → UI «Обработка» → путь `data/inbox` → «Запустить».

Подробнее: [docs/PIPELINE.md](docs/PIPELINE.md).

---

## Запуск пайплайна (кратко)

### CLI

```bash
cd nickel
pip install -r requirements.txt
cp ../.env.example ../.env

python cli.py pipeline document.pdf              # полный цикл → Neo4j + Qdrant
python cli.py pipeline report.docx --extractor ollama
python cli.py pipeline data.xlsx                 # Excel без LLM
```

### API — один файл

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload?extractor=auto" \
  -H "X-API-Key: KEY" -F "file=@report.pdf"
curl http://localhost:8000/api/v1/jobs/JOB_ID/logs -H "X-API-Key: KEY"
```

### API — папка

```bash
curl -X POST http://localhost:8000/api/v1/documents/ingest-folder \
  -H "Authorization: Bearer TOKEN" \
  -d '{"folder_path":"data/inbox","recursive":false}'
```

### Docker: файлы в inbox

```bash
docker cp ./reports/. nickel-api:/app/data/inbox/
# далее UI или ingest-folder API
```

---

## Архитектура

```
PDF / DOCX / XLSX
  → chunking + LLM extraction (Ollama / Yandex)
  → glossary + entity resolution + SHACL
  → Neo4j (граф) + Qdrant (векторы) + SQLite (факты, RBAC)
  → API: поиск, верификация, аналитика, экспорт MD/PDF/JSON-LD
```

### Хранилища

| Компонент | Назначение |
|-----------|------------|
| SQLite | Пользователи, глоссарий, факты, аудит, jobs |
| Neo4j | Граф сущностей |
| Qdrant | Семантический / гибридный поиск |

---

## Единый CLI

```bash
cd nickel
python cli.py serve              # API :8000
python cli.py pipeline FILE      # пайплайн
python cli.py export --topic "никель" --format pdf
python cli.py health
python cli.py mvp FILE           # legacy: только LLM extraction
```

---

## Аутентификация

1. Admin: `/admin/` или `POST /api/v1/auth/setup`
2. JWT: `POST /api/v1/auth/token` + `Authorization: Bearer …`
3. Или заголовок `X-API-Key`

| Роль | Права |
|------|-------|
| researcher | read, search, upload |
| analyst | + verify, export, synthesis |
| project_manager | + dashboard, audit |
| admin | все |
| external_partner | read/search + ACL документов |

---

## Frontend

React + Vite + Tailwind (стиль Nornfront). Страницы: **Обработка** (jobs, logs, batch), **Поиск**.

```bash
cd frontend && npm install && npm run dev   # :3000, proxy → API
```

---

## Тесты и CI

```bash
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
# или
cd nickel && pytest tests/ -v
```

GitHub Actions: `.github/workflows/ci.yml`.

---

## Структура репозитория

```
pars/
├── deploy/              # Docker Compose, api/, nginx/ (entrypoint, TLS)
├── frontend/            # React UI
├── nickel/              # Python: api/, services/, cli.py, tests/
├── docs/                # PIPELINE, DEPLOY, API
├── scripts/             # verify, smoke_test, generate_certs
├── docker-compose.yml   # → include deploy/
├── .env.example
└── README.md
```

---

## Конфигурация

См. [.env.example](.env.example). Ключевое:

| Переменная | Описание |
|------------|----------|
| `NEO4J_URI`, `NEO4J_PASSWORD` | Граф |
| `QDRANT_HOST`, `QDRANT_PORT` | Векторы |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | LLM |
| `EXTRACTOR_BACKEND` | auto \| ollama \| yandex |
| `STRICT_SHACL` | Блок Neo4j при ошибке SHACL |
| `INGEST_ROOTS` | Папки для batch ingest |
| `JWT_SECRET` | Мин. 32 символа |

---

## Чеклист функций

| # | Функция |
|---|---------|
| 1–10 | Ingest, LLM, glossary, graph, search, verify, RBAC, analytics, admin, export |
| — | React UI, jobs + logs, batch folder |
| — | Tests, CI, health/degradation, pinned deps |
| — | nginx в Docker (omstu pattern), TLS |

---

Hackathon R&D Knowledge Graph — Nickel project.
