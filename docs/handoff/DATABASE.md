# База данных

СУБД — **PostgreSQL 16** (единая реляционная база `uzassets`). ORM — SQLAlchemy 2.0
(async). Данные приложения хранятся в одной БД (>100 таблиц, 51 ORM-модель).
Схема данных (клон/дамп) — см. INFRASTRUCTURE.md → «Клон базы данных».

## Домены схемы

| Домен | Основные таблицы / модели |
|---|---|
| Пользователи и доступ | `user`, `user_sessions`, `rbac_v3` (роли/права/группы/гранты), `api_key`, `mfa`, `entity_watch` |
| Организационная структура | `company`, `company_library`, `board`, sectors/directions, `year_registry` |
| Проекты и задачи | `project`, `task`, `board`, `progress_snapshot`, `pmo` (спринты/RAID/расписание) |
| Финансовая отчётность | `financial` (report/line), `ifrs_report_history`, `finmodel`, `overview_matrix` |
| Финансовая модель | бизнес-план и КПЭ (`bp_kpi`), `credit`/`credit_scenario`/`loan_repayments`, `subsidies`, `elasticity`, `scenarios` |
| Производство / себестоимость | снапшоты в `system_config` (JSONB) |
| Закупки | `procurement` |
| Рейтинги / ESG / КУ | `rating`/`agency_rating`(+`_history`), `esg`, `governance` |
| Консультанты | `consultant` |
| Отчёты | `report_wizard` |
| Уведомления | `notification`, `telegram_outbox`, `admin_broadcast`, `announcement`, `status_update`, `comment` |
| Модерация | `moderation_submission`, `moderation_comment`, `moderation_rule` |
| Аудит | `audit_log`, `finmodel_audit_log`, `*_history` |
| ИИ | `ai`, `ai_conversation`, `ai_user_config`, `knowledge` |
| Интеграции | `external_api`, `custom_api`, `webhook`, `partner`, `api_key` |
| Настройки | `system_config` |

## Очереди

- **`telegram_outbox`** — исходящая очередь сообщений Telegram (уведомления, коды).
  Backend кладёт сообщение в таблицу; бот-воркер (`uza-tg-bot`) периодически
  опрашивает очередь (интервал/размер батча/ретраи настраиваются переменными
  `OUTBOX_POLL_SEC`, `OUTBOX_BATCH_SIZE`, `OUTBOX_MAX_RETRIES`) и доставляет их.
  Модель «транзакционный outbox»: запись в очередь идёт в той же транзакции, что и
  бизнес-данные, что исключает потерю уведомлений при сбое.
- **`moderation_submission`** — очередь заявок на согласование изменений
  (заявка → рассмотрение модератором → применение apply-обработчиком модуля).

Отдельного брокера сообщений (RabbitMQ/Kafka) нет — очереди реализованы таблицами
PostgreSQL; фоновая обработка — бот-воркером и apply-диспетчером модерации.

## Целостность и особенности

- **Аудит `audit_log`** ведётся в режиме «только добавление» (append-only) с
  контролем целостности (HMAC-цепочка); срок хранения — не менее 5 лет.
- **История изменений** ключевых сущностей — отдельными `*_history` таблицами.
- **JSONB** используется для вариативных снапшотов (производство, себестоимость,
  forensic-закупки) и настроек (`system_config`).
- **Отчётные периоды** управляются единым реестром годов (`year_registry`).
- **Шифрование полей** — чувствительные значения (напр. `telegram_chat_id`, коды
  MFA) хранятся зашифрованными (Fernet).

## Миграции

Два механизма, применяются при старте backend:

1. **Alembic** — версионируемые миграции схемы (каталог `backend/alembic/`).
2. **Runtime-миграции** (`app/core/runtime_migrations*.py`) — идемпотентные
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` +
   partial-индексы и точечные бэкофиллы; выполняются при запуске приложения,
   безопасны к повторному запуску (не падают на существующих объектах).

Роли БД: приложение работает под ролью наименьших привилегий (`uza_app`: DML без DDL
и без UPDATE/DELETE по `audit_log`); Alembic-миграции — под ролью с DDL-правами.
