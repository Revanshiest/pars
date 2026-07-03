# Deploy — Docker Compose

## Запуск

```bash
# Demo (HTTP на :8080, без TLS)
docker compose -f deploy/docker-compose.yml up -d --build

# Demo с self-signed HTTPS (:8443)
python scripts/generate_certs.py
docker compose -f deploy/docker-compose.yml up -d --build
# entrypoint подхватит deploy/nginx/certs/*.pem → https-selfsigned.conf

# Production Let's Encrypt (после DNS на DOMAIN)
# .env: DOMAIN=example.com EMAIL=admin@example.com
docker compose -f deploy/docker-compose.yml --profile init-cert run --rm certbot-issue
docker compose -f deploy/docker-compose.yml restart nginx
docker compose -f deploy/docker-compose.yml --profile certbot up -d certbot
```

## Nginx: выбор конфига (entrypoint.sh)

| Условие | Конфиг |
|---------|--------|
| Let's Encrypt для `$DOMAIN` | `https.conf.template` |
| `certs/cert.pem` + `key.pem` | `https-selfsigned.conf` |
| иначе | `http-only.conf` |

## Порты

| Host | Container | Назначение |
|------|-----------|------------|
| `${NICKEL_HTTP_PORT:-8080}` | 80 | UI + `/api/` |
| `${NICKEL_HTTPS_PORT:-8443}` | 443 | HTTPS |
| 8000 | api | Swagger (direct) |

## Структура nginx/

```
nginx/
├── Dockerfile
├── entrypoint.sh
├── http-only.conf
├── https-selfsigned.conf
├── https.conf.template   # Let's Encrypt
└── certs/                # self-signed (generate_certs.py)
```

**Отличие от omstu:** API Nickel уже на `/api/v1/…` — rewrite `/api/` → `/` не применяется.
