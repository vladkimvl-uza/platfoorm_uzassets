# Архитектура

## C4-модель

### Уровень 1 — Контекст

![Контекст](diagrams/c4_context.png)

Пользователи (руководство общества, отраслевые аналитики, работники предприятий,
консультанты) и контролирующие структуры (режим Read-Only) работают с платформой
через веб-браузер и Telegram. Платформа обменивается данными с внешними системами:
учётными системами предприятий (1С/ERP), электронной программой «Молиявий модель»,
системой корпоративного управления E-Kengash, средствами ЭЦП (E-IMZO) и
идентификации (ЕСИ OneID), мессенджером Telegram и почтовым сервером (SMTP).

### Уровень 2 — Контейнеры

![Контейнеры](diagrams/c4_container.png)

| Контейнер | Технология | Назначение |
|---|---|---|
| SPA | Vue 3 / TypeScript / Vite | Основной веб-интерфейс |
| Telegram Mini App (TWA) | Vue 3 / TWA SDK | Облегчённый доступ из Telegram |
| nginx (`uza-nginx`) | nginx 1.27 + brotli | TLS-терминация, reverse proxy, отдача статики |
| Backend API (`uza-backend`) | FastAPI / Python 3.12 / Uvicorn | REST API, бизнес-логика, интеграции |
| Telegram бот (`uza-tg-bot`) | aiogram 3 | Доставка уведомлений, обработка callbacks |
| СУБД (`uza-postgres`) | PostgreSQL 16 | Единая база данных |
| Backup-воркер (`uza-backup`) | cron + pg_dump + GPG | Периодическое шифрованное резервное копирование |

Все контейнеры — в одной приватной сети Docker (`uza-net`); наружу опубликован
только nginx (порты 80/443). PostgreSQL слушает только внутреннюю сеть.

### Уровень 3 — Компоненты (backend)

Слоистая архитектура, поток запроса:

```
HTTP → route (тонкий) → dependencies (аутентификация, RBAC-права, scope)
     → service (бизнес-логика) → unit of work (транзакция)
     → repository (SQLAlchemy) → PostgreSQL
```

Ключевые сквозные компоненты:

- **Auth / RBAC / MFA** — аутентификация (пароль + второй фактор), ролевая модель
  прав с повторной серверной проверкой на каждом запросе, ограничение области
  видимости по предприятиям/секторам.
- **Модерация** — изменения ограниченных пользователей ставятся в очередь на
  согласование (`gate_or_apply` → apply-обработчик по модулю).
- **Аудит** — журнал действий в режиме «только добавление» с контролем целостности.
- **Интеграционный шлюз** — приём данных из 1С/ERP, реестр внешних API, ключи
  программного доступа, исходящие webhooks.
- **Runtime-миграции** — идемпотентные `ALTER TABLE ... IF NOT EXISTS` при старте
  backend (в дополнение к Alembic).

Домены (сервисные пакеты): dashboard, exec_dashboard, financials (ifrs/nsbu/hlf),
business_plan, kpi, credit, invest, unit_cost, production, procurement/forensic,
ratings, esg, governance, consultants, projects/tasks, pmo, reporting, notifications,
moderation, audit, rbac_v3, companies, ai и другие (всего ~68 пакетов).

## Стратегия ветвления

Основная ветка — **`master`**: единственная защищённая долгоживущая ветка, всегда в
рабочем (деплоящемся) состоянии.

Рекомендуемый процесс:

- работа ведётся в короткоживущих feature-ветках `feature/<кратко>` от `master`;
- слияние в `master` через Pull Request с ревью; прямые пуши в `master` не приветствуются;
- `master` — источник автодеплоя: пуш в `master` разворачивается на VM автоматически
  (VM тянет `origin/master` по systemd-таймеру, см. INFRASTRUCTURE.md);
- теги релизов `vMAJOR.MINOR.PATCH` при значимых поставках;
- hotfix — ветка `hotfix/<кратко>` от `master`, ускоренное ревью и слияние.

Гейты качества перед слиянием:

- backend: `python -m py_compile` изменённых модулей; тесты `pytest` (testcontainers);
- frontend: `npx vite build` (эталонная прод-сборка; strict-режим `vue-tsc` не гейтует).

## Технологии (стек)

### Backend

| Слой | Средство (версия не ниже) |
|---|---|
| Каркас API | FastAPI (Python 3.12), Uvicorn |
| ORM / драйвер | SQLAlchemy 2.0 (async), asyncpg / psycopg |
| Миграции | Alembic + runtime-миграции |
| Валидация | Pydantic 2 |
| Аутентификация | PyJWT (RS256), bcrypt |
| Шифрование полей / целостность | cryptography (Fernet), HMAC |
| Ограничение частоты | slowapi |
| Обработка данных / импорт | pandas, openpyxl |
| Telegram | aiogram 3 |
| Наблюдаемость | prometheus-client, sentry-sdk |
| СУБД | PostgreSQL 16 |

### Frontend

Vue 3, Vite, TypeScript, Pinia, Vue Router, Chart.js. Telegram Mini App — отдельная
Vue 3 сборка (TWA SDK). Статика собирается в образ nginx (multi-stage), сжимается
brotli на этапе сборки.

### Инфраструктура

nginx 1.27 (TLS, brotli), Docker / Docker Compose, Ubuntu 24.04 LTS.

## Интеграции

### Клиент ↔ сервер

Взаимодействие фронтенда с backend — **REST API** (JSON) под префиксом `/api/`
(nginx проксирует `/api/ → backend:8000`). Аутентификация — JWT (RS256) в заголовке
`Authorization: Bearer`, обязательный `kid` в заголовке токена. Основные группы
эндпоинтов (72 роутера):

| Область | Префиксы (примеры) |
|---|---|
| Аутентификация / сессии / MFA | `/auth/*`, `/sessions/*`, `/mfa/*` |
| Пользователи, роли, права | `/rbac/v3/*`, `/users/*`, `/directory/*` |
| Компании / рабочее пространство | `/companies/*` |
| Финансы | `/financials/*`, `/financials-portfolio/*`, `/hlf/*` |
| Бизнес-план / КПЭ | `/bp/*`, `/kpi/*` |
| Кредиты / инвестиции | `/credit/*`, `/invest*`, `/loan*` |
| Производство / себестоимость | `/production/*`, `/unit-cost/*` |
| Закупки | `/procurement/*`, `/forensic/*` |
| Рейтинги / ESG / КУ | `/ratings/*`, `/esg/*`, `/governance/*` |
| Проекты / задачи / PMO | `/projects/*`, `/tasks/*`, `/pmo/*`, `/boards/*` |
| Консультанты | `/consultants/*` |
| Отчёты | `/report-wizard/*`, `/reporting/*` |
| Уведомления | `/notifications/*` |
| Модерация / аудит | `/moderation/*`, `/audit/*` |
| Дашборды | `/dashboard/*`, `/executive-dashboard/*` |
| Вложения | `/attachments/*` |
| Интеграционный шлюз | `/external-apis/*`, `/api-keys/*`, `/webhooks/*` |

Реалтайм-доставка внутрисистемных уведомлений — WebSocket.
Полная спецификация — OpenAPI (`/api/openapi.json`, Swagger UI `/api/docs`).

### Внешние системы

| Система | Направление | Транспорт |
|---|---|---|
| Учётные системы 1С/ERP предприятий | приём данных (PUSH) | HTTPS/JSON, пакеты 200–1000 записей, идемпотентность |
| «Молиявий модель» (внешняя ИС) | двусторонний обмен показателями | REST/JSON |
| E-Kengash (корп. управление) | приём сведений о заседаниях/советах | REST/JSON |
| E-IMZO | подтверждение действий ЭЦП | по регламенту E-IMZO |
| ЕСИ OneID | идентификация пользователей (каркас, off по умолчанию) | OAuth2/OIDC |
| Telegram | уведомления, Mini App, callbacks | Bot API |
| SMTP | e-mail-уведомления | SMTP |

Каталог интеграционных сервисов 1С/ERP оформлен машиночитаемо (`docs/integration/`,
по O'zMSt 151:2024): реестр услуг, описание интерфейса, SLA.
