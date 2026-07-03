# Nickel — R&D Knowledge Graph Platform

Платформа для извлечения, хранения, верификации и анализа знаний из научно-технической документации в области горной металлургии (никель, HL, арктические условия).

**Стек:** FastAPI · SQLite · Neo4j · Qdrant · Ollama/Yandex GPT · RDF/SHACL · reportlab

---

## Быстрый старт (жюри / демо)

### Быстрая проверка

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

Проверяет: compile, pytest (16), smoke API, frontend build, docker-compose config.

```bash
python scripts/generate_certs.py
docker compose up -d --build
```

| Сервис | URL |
|--------|-----|
| **Web UI** (nginx) | http://localhost:8080 |
| **Web UI** (HTTPS) | https://localhost:8443 |
| API + Swagger | http://localhost:8000/docs |
| Admin (пользователи) | http://localhost:8080/admin/ |
| Neo4j Browser | http://localhost:7474 |

**Первый вход:** откройте `/admin/` → создайте admin → сохраните API-ключ.

### 2. Локально (без Docker)

```bash
cd nickel
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env

# Neo4j + Qdrant должны быть доступны (см. .env)
python cli.py serve
```

### 3. Проверка здоровья

```bash
python cli.py health          # все компоненты
python cli.py health --kind ready   # readiness (SQLite обязателен)
curl http://localhost:8000/live     # liveness probe
curl http://localhost:8000/metrics  # JSON-метрики
```

---

## Единый CLI

Все операции через `nickel/cli.py`:

```bash
cd nickel

python cli.py serve                    # API-сервер
python cli.py pipeline document.pdf    # полный пайплайн → Neo4j + Qdrant
python cli.py export --topic "никель" --format pdf
python cli.py health
python cli.py mvp document.pdf         # legacy: только LLM-extraction
python cli.py visualize outputs/graph.json
```

---

## Архитектура

```
Документ (PDF/DOCX/XLSX)
    → chunking + glossary normalization
    → LLM extraction (Ollama / Yandex)
    → entity resolution + SHACL validation
    → Neo4j (граф) + Qdrant (векторы) + SQLite (факты, RBAC, аудит)
    → API: поиск, верификация, аналитика, экспорт
```

### Хранилища

| Компонент | Назначение |
|-----------|------------|
| **SQLite** (`PLATFORM_DB`) | Пользователи, API-ключи, глоссарий, факты, версии, аудит, уведомления |
| **Neo4j** | Граф сущностей и связей, обход соседей |
| **Qdrant** | Семантический поиск по чанкам и сущностям |

### Graceful degradation

При недоступности Neo4j или Qdrant API остаётся частично работоспособным:

- SQLite down → `503` на большинстве эндпоинтов
- Qdrant down → семантический/гибридный поиск `503`; glossary, auth, export MD работают
- Neo4j down → graph search `503`; остальное через SQLite/Qdrant

Статус: `GET /health` (`ok` | `degraded` | `unavailable`).

---

## Аутентификация и RBAC

1. **Первый admin:** `POST /api/v1/auth/setup` или UI `/admin/`
2. **JWT:** `POST /api/v1/auth/token` с `{"api_key": "..."}` → `Authorization: Bearer <token>`
3. **Или:** заголовок `X-API-Key`

| Роль | Права |
|------|-------|
| `researcher` | read, search, upload |
| `analyst` | + verify, edit_graph, export, synthesis |
| `project_manager` | + dashboard, compare, audit |
| `admin` | все (`*`) |
| `external_partner` | read/search; ACL по документам (`internal`/`partner`/`public`) |

---

## Основные сценарии API

Полная справка: [docs/API.md](docs/API.md) и Swagger `/docs`.

```bash
# Загрузка документа
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: YOUR_KEY" -F "file=@report.pdf"

# Гибридный поиск
curl -X POST http://localhost:8000/api/v1/search/hybrid \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "heap leaching nickel cold climate", "limit": 10}'

# Литобзор + экспорт PDF
curl -X POST http://localhost:8000/api/v1/synthesis/literature-review \
  -H "Authorization: Bearer TOKEN" \
  -d '{"topic": "никель HL холодный климат", "use_llm": true}'

curl -X POST http://localhost:8000/api/v1/export \
  -H "Authorization: Bearer TOKEN" \
  -d '{"topic": "никель", "format": "pdf"}'
```

---

## Тесты

```bash
cd nickel
pip install -r requirements-dev.txt
pytest tests/ -v
```

CI: `.github/workflows/ci.yml` — compile + pytest на push/PR.

---

## Конфигурация

См. `.env.example`. Ключевые переменные:

| Переменная | Описание |
|------------|----------|
| `NEO4J_URI`, `NEO4J_PASSWORD` | Граф |
| `QDRANT_HOST`, `QDRANT_PORT` | Векторный индекс |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | LLM extraction / synthesis |
| `EXTRACTOR_BACKEND` | `auto` \| `ollama` \| `yandex` |
| `STRICT_SHACL` | Блокировать Neo4j при ошибке SHACL |
| `JWT_SECRET` | Мин. 32 символа |
| `LIT_REVIEW_USE_LLM` | LLM-синтез литобзора |
| `SKIP_OLLAMA_HEALTH` | Пропустить проверку Ollama в health |

---

## Структура репозитория

```
pars/
├── deploy/                 # Docker: compose, api, nginx
│   ├── docker-compose.yml
│   ├── api/Dockerfile
│   └── nginx/              # edge reverse proxy (TLS)
├── frontend/               # React UI (Nornfront style)
├── nickel/                 # Python backend + CLI
│   ├── api/
│   ├── services/
│   ├── tests/
│   └── cli.py
├── scripts/                # verify, smoke_test, generate_certs
├── docs/API.md
├── docker-compose.yml      # include → deploy/
└── README.md
```

---

## Реализованные требования (чеклист)

| # | Функция | Статус |
|---|---------|--------|
| 1 | Ingest PDF/DOCX/XLSX | ✅ |
| 2 | LLM extraction + ontology | ✅ |
| 3 | Glossary normalization | ✅ |
| 4 | Graph storage + versioning | ✅ |
| 5 | Hybrid search + filters | ✅ |
| 6 | Verification workflow | ✅ |
| 7 | RBAC, audit, TLS | ✅ |
| 8 | Analytics, gaps, lit review | ✅ |
| 9 | Admin UI | ✅ |
| 10 | Export MD/JSON-LD/PDF | ✅ |
| — | README + API docs | ✅ |
| — | Tests + CI | ✅ |
| — | Health / graceful degradation | ✅ |
| — | Unified CLI | ✅ |
| — | Pinned dependencies | ✅ |

---

## Лицензия / контакты

Hackathon R&D Knowledge Graph — Nickel project.
