# Документация Nickel R&D Knowledge Graph

| Документ | Содержание |
|----------|------------|
| [../README.md](../README.md) | Обзор проекта, быстрый старт |
| [PIPELINE.md](PIPELINE.md) | **Запуск пайплайна** (CLI, API, UI, batch) |
| [DEPLOY.md](DEPLOY.md) | Docker, nginx, TLS, volumes |
| [API.md](API.md) | Справочник REST API |

## Быстрые ссылки

```bash
# Docker
docker compose up -d --build

# Пайплайн одного файла
cd nickel && python cli.py pipeline document.pdf

# Тесты
cd nickel && pytest tests/ -v
```
