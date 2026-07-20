# Единая платформа трансформации — техническая документация

Веб-платформа мониторинга финансово-хозяйственной деятельности и трансформации
государственных предприятий: сбор и онлайн-анализ финансовой отчётности (МСФО/НСБУ),
исполнения бизнес-планов и КПЭ, кредитного портфеля, инвестпроектов, производственных
показателей и себестоимости, закупок, рейтингов, ESG и корпоративного управления,
портфеля проектов и задач. Ролевой доступ, модерация изменений, журнал аудита.

## Состав документации

| Документ | Содержание |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | C4-модель (контекст/контейнеры/компоненты), стратегия ветвления, технологии, список интеграций клиент↔сервер и внешних систем |
| [INFRASTRUCTURE.md](INFRASTRUCTURE.md) | Схема развёртывания, Docker, параметры серверов, текущая нагрузка, планирование мощностей, клон БД |
| [DATABASE.md](DATABASE.md) | Схема БД (домены), очереди, миграции |
| [RUNBOOK.md](RUNBOOK.md) | Эксплуатация: деплой, резервное копирование/восстановление, инциденты, типовые операции |
| [SNAPSHOT.md](SNAPSHOT.md) | Порядок формирования передаваемого снимка кода |
| [diagrams/](diagrams/) | PNG-схемы (C4, инфраструктура) |

## Структура репозитория

```
backend/          FastAPI-приложение (Python 3.12)
  app/
    api/routes/   72 REST-роутера (тонкий HTTP-слой)
    services/     бизнес-логика (68 доменных пакетов)
    repositories/ доступ к данным (SQLAlchemy)
    models/       ORM-модели (51 модель)
    schemas/      Pydantic-схемы (валидация/сериализация)
    core/         безопасность, конфиг, runtime-миграции
    uow/          Unit of Work
  docker-compose.yml
  Dockerfile
frontend/         SPA (Vue 3 + TypeScript + Vite)
frontend-twa/     Telegram Mini App (Vue 3)
bot/              Telegram бот-воркер (aiogram 3)
nginx/            reverse proxy + сборка фронта (multi-stage Dockerfile)
docs/             документация
ops/              автодеплой (systemd-таймер)
```

## Быстрый старт (локально)

Требуется Docker + Docker Compose.

```bash
cd backend
cp ../.env.example .env         # заполнить POSTGRES_PASSWORD и ключи (см. .env.example)
# сгенерировать ключи: JWT RS256, Fernet, HMAC (см. RUNBOOK.md → «Ключи»)
docker compose up -d --build    # dev-профиль: postgres + backend + фронт-сборка
```

Полный стек (с nginx/TLS и резервным копированием):

```bash
docker compose --project-directory . -f backend/docker-compose.yml \
  --profile production up -d --build
```

Приложение: `https://<host>/` (SPA), API: `https://<host>/api/`,
интерактивная документация API (при `ENABLE_DOCS_IN_PRODUCTION=true`): `/api/docs`.

## Слой архитектуры (backend)

Запрос проходит слои: **route → dependencies → service → unit of work → repository → БД**.
Роутеры тонкие (без прямого доступа к БД); бизнес-логика в сервисах; доступ к данным в
репозиториях. Изменения данных выполняются в единой транзакции вместе с записью аудита.
