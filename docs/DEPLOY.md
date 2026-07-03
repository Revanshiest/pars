# Развёртывание (Docker)

## Быстрый старт

```bash
git clone <repo>
cd pars
cp .env.example .env
# Отредактировать JWT_SECRET (мин. 32 символа)

docker compose up -d --build
```

## URL после запуска

| Сервис | URL |
|--------|-----|
| Web UI | http://localhost:8080 |
| HTTPS (self-signed) | https://localhost:8443 |
| API Swagger | http://localhost:8000/docs |
| Admin | http://localhost:8080/admin/ |
| Neo4j Browser | http://localhost:7474 (neo4j / nickel_kg_pass) |
| Qdrant | http://localhost:6333/dashboard |

## Первый пользователь

1. В `.env` задайте admin:
   ```
   AUTH_ADMIN=admin@company.ru|Administrator|your-secret-api-key-min-16-chars
   ```
2. Перезапустите API (`docker compose up -d --build` или `python cli.py serve`)
3. http://localhost:8080/admin/ → войти ключом из `AUTH_ADMIN`
4. Создайте остальных пользователей в админке
5. http://localhost:8080 → войти по ключу любого пользователя

`POST /api/v1/auth/setup` доступен только если `AUTH_ADMIN` **не** задан (режим разработки).

## TLS

**Self-signed (демо):**

```bash
python scripts/generate_certs.py
docker compose up -d --build
# nginx entrypoint → https-selfsigned.conf
```

**Let's Encrypt:**

```env
DOMAIN=your.domain.com
EMAIL=admin@your.domain.com
```

```bash
docker compose --profile init-cert run --rm certbot-issue
docker compose restart nginx
docker compose --profile certbot up -d certbot
```

## Nginx (паттерн omstu-containered)

`deploy/nginx/entrypoint.sh` выбирает конфиг:

| Условие | Файл |
|---------|------|
| LE cert для `$DOMAIN` | `https.conf.template` |
| `certs/cert.pem` | `https-selfsigned.conf` |
| иначе | `http-only.conf` |

Особенности:
- `resolver 127.0.0.11` — Docker DNS, nginx не падает при старте
- `set $nickel_api api:8000` — отложенный resolve upstream

## Volumes

| Volume | Содержимое |
|--------|------------|
| `api_data` | uploads, inbox, outputs, platform.db, jobs.db |
| `neo4j_data` | Граф |
| `qdrant_data` | Векторы |

Копирование файлов в inbox:

```bash
docker cp ./reports/. nickel-api:/app/data/inbox/
```

## Локально без Docker

```bash
cd nickel
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example ../.env

# Neo4j + Qdrant должны быть доступны
python cli.py serve
```

Frontend dev:

```bash
cd frontend && npm install && npm run dev
# http://localhost:3000 → proxy /api → :8000
```

## Проверка

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify.ps1
```

## Переменные compose

| Переменная | Default | Описание |
|------------|---------|----------|
| `NICKEL_HTTP_PORT` | 8080 | Host port → nginx:80 |
| `NICKEL_HTTPS_PORT` | 8443 | Host port → nginx:443 |
| `JWT_SECRET` | (change me!) | JWT signing |
| `OLLAMA_BASE_URL` | host.docker.internal:11434 | LLM |

Полный список: [.env.example](../.env.example).
