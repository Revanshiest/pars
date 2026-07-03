# API Reference — Nickel R&D Knowledge Graph

Base URL: `http://localhost:8000` (Docker: порт `8000`, HTTPS через nginx: `8443`)

Интерактивная документация: **`/docs`** (Swagger), **`/redoc`**

---

## Аутентификация

| Метод | Заголовок |
|-------|-----------|
| API Key | `X-API-Key: <key>` |
| JWT Bearer | `Authorization: Bearer <token>` |
| SSO (опционально) | `X-Remote-User` / `X-Forwarded-Email` при `TRUST_SSO_HEADERS=true` |

### Bootstrap

```
POST /api/v1/auth/setup
{"email": "admin@org.local", "name": "Admin", "api_key": "optional-min-16-chars"}

POST /api/v1/auth/token
{"api_key": "..."}
→ {"access_token": "...", "token_type": "bearer", "expires_in": 86400}

GET  /api/v1/auth/status
GET  /api/v1/auth/me          (auth required)
```

---

## Health & Monitoring

| Endpoint | Назначение | Auth |
|----------|------------|------|
| `GET /live` | Liveness (процесс жив) | нет |
| `GET /ready` | Readiness (SQLite OK) | нет |
| `GET /health` | Полная проверка компонентов | нет |
| `GET /metrics` | JSON: facts, users, components | нет |

**Ответ `/health`:**
```json
{
  "status": "ok|degraded|unavailable",
  "components": {
    "sqlite": {"status": "ok", "detail": "users=3", "latency_ms": 1.2},
    "neo4j": {"status": "ok", "detail": "120 entities, 340 rels"},
    "qdrant": {"status": "ok", "detail": "collections ready"},
    "ollama": {"status": "degraded", "detail": "optional: ..."}
  }
}
```

---

## Documents & Pipeline

| Method | Path | Permission | Описание |
|--------|------|------------|----------|
| POST | `/api/v1/documents/upload` | upload | Загрузка файла → background job |
| POST | `/api/v1/documents/ingest-folder` | upload | Пакетная обработка папки на сервере |
| GET | `/api/v1/ingest/folders` | read | Доступные папки для ingest |
| GET | `/api/v1/jobs` | read | Список задач (`?active=true`) |
| GET | `/api/v1/jobs/{id}` | read | Статус задачи |
| GET | `/api/v1/jobs/{id}/logs` | read | Append-only лог (`?since_id=0`) |
| GET | `/api/v1/jobs/{id}/children` | read | Дочерние задачи пакета |

**Upload:** `multipart/form-data`, поле `file`. Query: `extractor=ollama|yandex|auto`.

Поддерживаемые форматы: `.pdf`, `.md`, `.txt`, `.docx`, `.xlsx`, `.xls`.

---

## Search

| Method | Path | Permission | Описание |
|--------|------|------------|----------|
| POST | `/api/v1/search/semantic` | search | Семантический поиск (Qdrant) |
| POST | `/api/v1/search/graph` | search | Обход графа Neo4j |
| POST | `/api/v1/search/agent` | search | Knowledge agent (tools + optional LLM) |
| POST | `/api/v1/search/filtered` | search | Поиск с фильтрами |
| POST | `/api/v1/search/hybrid` | search | Vector + graph + facts ranking |
| POST | `/api/v1/search/compare-practices` | compare | Сравнение практик |
| POST | `/api/v1/search/numeric` | search | Числовые запросы |

**Filtered / hybrid body (пример):**
```json
{
  "query": "heap leaching nickel",
  "limit": 10,
  "year_from": 2020,
  "document_kind": "publication",
  "min_confidence": 0.6,
  "geography": "RU"
}
```

`document_kind`: `patent` | `regulation` | `publication` | `report` | `experiment_catalog`

---

## Facts & Verification

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/facts` | read |
| GET | `/api/v1/facts/{id}` | read |
| GET | `/api/v1/facts/{id}/versions` | read |
| POST | `/api/v1/facts/{id}/verify` | verify |
| POST | `/api/v1/facts/{id}/assign` | verify |
| DELETE | `/api/v1/facts/{id}/assign` | verify |
| GET | `/api/v1/verification/queue` | verify |
| GET | `/api/v1/verification/my-queue` | verify |
| POST | `/api/v1/verification/claim` | verify |

**Verify body:** `{"status": "verified|rejected|pending|in_review", "notes": "..."}`

---

## Glossary

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/glossary` | glossary_read |
| POST | `/api/v1/glossary` | glossary_write |
| POST | `/api/v1/glossary/lookup` | glossary_read |
| GET | `/api/v1/glossary/expand?q=...` | glossary_read |

---

## Analytics & Synthesis

| Method | Path | Permission |
|--------|------|------------|
| POST | `/api/v1/synthesis/literature-review` | synthesis |
| GET | `/api/v1/analytics/sources-breakdown` | read |
| GET | `/api/v1/analytics/gaps` | read |
| POST | `/api/v1/analytics/gaps/ontology` | read |
| GET | `/api/v1/analytics/recommendations` | read |
| POST | `/api/v1/analytics/compare` | compare |
| GET | `/api/v1/dashboard` | dashboard |

**Literature review:**
```json
{"topic": "никель HL арктика", "geography": "RU", "min_confidence": 0.5, "use_llm": true}
```

**Ontology gaps:**
```json
{"query": "холодный климат + HL + Ni"}
```
или `{"material": "Ni", "process": "HL", "climate": "cold"}`

---

## Export

| Method | Path | Permission |
|--------|------|------------|
| POST | `/api/v1/export` | export |
| GET | `/api/v1/export/{topic}/download?format=md\|pdf\|jsonld` | export |

**Export body:** `{"topic": "никель", "format": "md|pdf|jsonld"}`

---

## Graph Editor

| Method | Path | Permission |
|--------|------|------------|
| POST | `/api/v1/graph/triples` | edit_graph |
| PATCH | `/api/v1/graph/triples/{id}` | edit_graph |
| DELETE | `/api/v1/graph/triples/{id}` | edit_graph |
| GET | `/api/v1/graph/edits` | read |
| GET | `/api/v1/graph/stats` | read |

---

## Documents ACL

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/documents` | read |
| PATCH | `/api/v1/documents/{source_document}/access` | admin |

**Access levels:** `internal` | `partner` | `public`

---

## Admin & Audit

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/admin/users` | admin |
| POST | `/api/v1/admin/users` | admin |
| PATCH | `/api/v1/admin/users/{id}` | admin |
| DELETE | `/api/v1/admin/users/{id}` | admin |
| POST | `/api/v1/admin/users/{id}/rotate-key` | admin |
| GET | `/api/v1/admin/roles` | admin |
| GET | `/api/v1/audit` | audit |

UI: **`/admin/`** — управление пользователями без curl.

---

## Notifications & Subscriptions

| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/v1/notifications` | read |
| POST | `/api/v1/notifications/{id}/read` | read |
| GET | `/api/v1/subscriptions` | subscribe |
| POST | `/api/v1/subscriptions` | subscribe |

---

## Ontology

```
GET /api/v1/ontology
→ {"node_types": [...], "relations": [...]}
```

---

## Коды ответов

| Code | Ситуация |
|------|----------|
| 401 | Нет auth |
| 403 | Нет permission / ACL |
| 503 | Компонент недоступен (graceful degradation) |
| 404 | Ресурс не найден |

Все mutating-операции пишутся в `audit_log` (SQLite).

---

## CLI-эквиваленты

```bash
python cli.py serve
python cli.py pipeline doc.pdf
python cli.py export --topic "никель" --format pdf --out report.pdf
python cli.py health
```
