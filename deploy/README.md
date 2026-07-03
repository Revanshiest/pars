# Deploy — Docker Compose

Единая точка входа для production/demo.

```bash
# из корня репозитория
python scripts/generate_certs.py
docker compose up -d --build
# или явно:
docker compose -f deploy/docker-compose.yml up -d --build
```

## Сервисы

| Контейнер | Роль | Порт (host) |
|-----------|------|-------------|
| `nickel-nginx` | Reverse proxy TLS + HTTP | **8080** (UI+API), **8443** (HTTPS) |
| `nickel-frontend` | SPA (static) | internal :80 |
| `nickel-api` | FastAPI | **8000** (Swagger/direct) |
| `nickel-neo4j` | Graph DB | 7474, 7687 |
| `nickel-qdrant` | Vector DB | 6333 |

## Структура

```
deploy/
├── docker-compose.yml    # полный стек
├── api/
│   └── Dockerfile        # Python API image
└── nginx/
    ├── Dockerfile        # edge nginx image
    ├── nginx.conf        # маршрутизация UI + API
    └── certs/            # TLS (генерируются локально)
```

Маршрутизация nginx:
- `/` → frontend (React SPA)
- `/api/` → api:8000
- `/admin`, `/health`, `/live`, `/ready`, `/metrics` → api

HTTP без TLS: **http://localhost:8080** (порт 8080 внутри nginx — plain proxy).
