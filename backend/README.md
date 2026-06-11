# UzAssets Platform

> Единая платформа трансформации — миграция легасиа `index.html` (~5 МБ, 66 477 строк vanilla JS) на современный full-stack: **FastAPI + Vue 3 + PostgreSQL**.

---

## Архитектура

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Vue 3 SPA   │───▶│  FastAPI     │───▶│ PostgreSQL 16│
│  Vite + TS   │    │  async       │    │              │
│  Pinia       │    │  SQLAlchemy  │    │  pgcrypto    │
│  Tailwind    │    │  Alembic     │    │  pg_trgm     │
└──────────────┘    └──────────────┘    └──────────────┘
       :5173              :8000               :5432
```

| Слой | Технология |
|---|---|
| Backend | FastAPI 0.115, Python 3.12, SQLAlchemy 2.0 (async), Alembic, pydantic-settings |
| Frontend | Vue 3.5, Vite 5, TypeScript 5.6, Pinia, Vue Router, Tailwind 3.4, Axios |
| DB | PostgreSQL 16 (pgcrypto, pg_trgm) |
| **Auth** | **Локальная: bcrypt + JWT (access + refresh). Без внешних IdP.** |
| AI | Anthropic Claude (Claude Opus 4.7 default) |
| Orchestration | Docker Compose (dev) → Coolify на uzcloud.uz (prod) |

---

## Быстрый старт

```bash
cp .env.example .env                                    # отредактировать JWT_SECRET
bash scripts/generate-keys.sh                           # RSA + Fernet + HMAC + self-signed TLS
docker compose up -d --build                            # postgres + backend + frontend
docker compose exec backend alembic upgrade head        # 56 таблиц + 22 роли + 10 секторов
```

Для полного стека с TLS-edge и backup'ами:

```bash
docker compose --profile production up -d --build       # + nginx + backup
```

Откроется на:
- http://localhost:5173 — Vue SPA (dev)
- http://localhost:8000/docs — Swagger UI (dev)
- https://localhost — Vue через nginx (production profile)
- http://localhost:8000/health/ready — проверка БД
- ИБ-каркас: см. [`docs/security.md`](docs/security.md)

---

## Модель доступа: 22 платформенные роли

Семантика и идентификаторы ролей зафиксированы в коде (`code` в таблице `roles`).

### Административные

| Код | Название | Описание |
|---|---|---|
| `admin` | Администратор | Полный системный администратор |
| `organization` | Пользователь организации | Работает в рамках данных своей организации |

### Финансовые / отраслевые специалисты

| Код | Название | Описание |
|---|---|---|
| `lawyer` | Юрист | AR/AP, претензии, суд |
| `financier` | Финансист | Кредиты, формы, дашборды, частично treasury/procurement |
| `debt` | Специалист по задолженности | Реестр долгов, кредитов, импорт/аудит |
| `investment` | Пользователь инвестиций | Инвестиционные страницы и дашборды |
| `finmodel` | Пользователь финмодели | Финмодель и производственное планирование |

### Стратегические / надзорные

| Код | Название | Описание |
|---|---|---|
| `monitoring` | Мониторинг | Кросс-модульный наблюдатель с широкими дашбордами |
| `fid` | FID | Стратегические дашборды (инвест/кредит/финмодель), edit ограничен |
| `audit_viewer` | Аудит | View-only во всех процессах утверждения |

### Иерархия одобрения (department chain)

| Код | Уровень | Роль |
|---|---|---|
| `initiator` | 0 | Инициатор процесса |
| `department_worker` | 1 | Сотрудник отдела (создаёт заявки) |
| `department_head` | 2 | Руководитель отдела (утверждает заявки) |
| `department_director` | 3 | Директор (директорский уровень утверждения) |
| `plan_department` | — | Плановый отдел (рассмотрение/возврат/закрытие) |
| `purchase_department` | — | Внутренний отдел закупок (участие/утверждение) |

### Procurement

| Код | Название | Описание |
|---|---|---|
| `procurement_owner` | Владелец закупок | Утверждённые заявки, тендеры, контракты, платежи по ним |

### Treasury / Финансовый контроль

| Код | Уровень | Роль |
|---|---|---|
| `finance_controller` | — | Финансовый контролёр (утверждение платежей по контракту) |
| `treasure_user` | — | Казначейство (платежи, бюджеты, отчёты) |
| `mdm_steward` | — | MDM-стюард (качество мастер-данных в платёжных процессах) |
| `cfo_department` | — | CFO-департамент (годовые бюджеты, лимиты) |
| `cfo_committee` | 4 | Комиссия CFO (утверждение в платёжных процессах) |

> Процессы одобрения (`worker → head → director`, `initiator → mdm → finance_controller → treasure → cfo_dept → cfo_committee`) реализуются через таблицы `approval_workflows` / `approval_workflow_instances` / `approval_steps` — добавляются в Часть 9 (Procurement) и Часть 10 (Treasury).

---

## Структура репозитория

```
uzassets-platform/
├── docker-compose.yml
├── .env.example
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 20260504_1200_0001_initial.py    ← все 56 таблиц + 22 роли + 10 секторов
│   ├── scripts/
│   │   └── init.sql                             ← pgcrypto, uuid-ossp, pg_trgm
│   └── app/
│       ├── main.py                              ← FastAPI app
│       ├── config.py                            ← pydantic-settings
│       ├── database.py                          ← async engine + session
│       ├── api/routes/                          ← REST endpoints (растёт по частям)
│       └── models/                              ← 18 файлов, 56 таблиц
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js                       ← UZA design tokens
    ├── index.html
    └── src/
        ├── main.ts
        ├── App.vue
        ├── router/                              ← Vue Router + auth guard
        ├── stores/auth.ts                       ← Pinia auth store
        ├── api/client.ts                        ← Axios + JWT interceptor
        ├── views/                               ← Login, Dashboard, Companies, AppShell
        └── assets/main.css                      ← Tailwind + UZA tokens
```

---

## Схема БД (56 таблиц)

| Модуль | Таблицы |
|---|---|
| **Auth & users** (9) | `users`, `roles`, `permissions`, `groups`, `role_by_email`, `user_sessions`, `user_role`, `role_permission`, `user_group` |
| **Org structure** (4) | `sectors`, `directions`, `companies`, `company_directions` |
| **Tasks** (4) | `tasks`, `task_comments`, `task_attachments`, `task_history` |
| **Boards (Kanban)** (3) | `boards`, `board_columns`, `board_cards` |
| **Ratings** (3) | `ratings`, `rating_metrics`, `rating_history` |
| **ESG** (4) | `esg_metrics`, `esg_issues`, `esg_notes`, `esg_years_tracked` |
| **Financials** (3) | `financial_reports`, `financial_lines`, `financial_models` |
| **KPI / BP** (5) | `kpi_records`, `kpi_comments`, `kpi_drafts`, `business_plans`, `business_plan_comments` |
| **Procurement** (4) | `procurement_contracts`, `procurement_data`, `product_clusters`, `procurement_benchmarks` |
| **Governance** (3) | `governance_data`, `governance_raw`, `board_members` |
| **Credit** (3) | `loans`, `loan_archive`, `credit_portfolio_meta` |
| **Misc** (11) | `announcements`, `audit_log`, `comments`, `notes`, `year_registry`, `system_config`, `ai_config`, `ai_access`, `ai_history`, `telemetry_log`, `consultant_imports` |

### Ключевые архитектурные решения

- **Local auth only** — bcrypt-хэш паролей, JWT access (8ч) + refresh (30 дней) с серверной отзываемостью через `user_sessions`. Поддержка lockout (`failed_login_attempts`, `locked_until`).
- **User scope** — `organization_id` (для `organization`-роли), `department` (для иерархии одобрения), `supervisor_id` (для построения цепочки утверждения), `allowed_sectors` / `allowed_companies` (для аналитики).
- **Procurement: `is_dirty` флаг** — все KPI-аггрегаты крутятся только на чистых записях.
- **Procurement: `product_clusters`** — log-scale buckets, `bucket_size=0.5`, `k_cap=7`.
- **Procurement: `procurement_benchmarks.median_price`** — медиана, не weighted mean.
- **Governance: `governance_data` ≠ `governance_raw`** — структурированные редактируемые данные vs Excel-снапшоты для AI.
- **`year_registry`** — единый источник истины, никаких хардкодов годов.
- **Audit log: append-only** — индексы на `(actor, action, time)` и `(entity_type, entity_id, time)`.

---

## Roadmap миграции

| Часть | Содержание | Статус |
|---|---|---|
| 1 | Структура проекта, Docker Compose, схема PostgreSQL (56 таблиц), Alembic, FastAPI/Vue скелет, 22 роли | ✅ |
| 2 | Auth: bcrypt + JWT issue/refresh, RBAC `require_permission()`, seed-пользователи, login UI | — |
| 3 | legacy store → Postgres migration script (`--dry-run` / `--apply`) | — |
| 4 | Companies + Dashboard endpoints + Vue списки | — |
| 5 | Tasks + Boards (Kanban с drag-and-drop) | — |
| 6 | Ratings + ESG | — |
| 7 | Financials editor (IFRS / NSBU) | — |
| 8 | KPI editor + Business Plan + anti-loss draft system | — |
| 9 | Procurement analytics + price clustering + **approval workflows** | — |
| 10 | Governance + Credit Portfolio + **Treasury** + Audit Log | — |
| 11 | AI Analytics + Reports + Export + UZA design system polish | — |

---

## Команды Alembic

```bash
docker compose exec backend alembic upgrade head            # применить
docker compose exec backend alembic downgrade -1            # откат
docker compose exec backend alembic revision --autogenerate -m "msg"
docker compose exec backend alembic current
docker compose exec backend alembic history
```

## Production deploy на uzcloud.uz

См. отдельный документ `docs/deployment.md` (Часть 11). Целевой сайзинг: ~5 vCPU / 14 GB RAM / 140 GB SSD на три ресурса (postgres / backend / frontend), data sovereignty в Узбекистане.
