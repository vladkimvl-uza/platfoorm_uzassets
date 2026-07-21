# Runbook (эксплуатация)

> Снимок: коммит **c9f29f3**, ветка **master**, дата **2026-07-21**.
> Прод-VM: **89.126.221.64** (Ubuntu 24.04.4 LTS, 2 vCPU, 3.8 GiB RAM, диск 38 GB).
> Смежные документы: `ARCHITECTURE.md`, `INFRASTRUCTURE.md`, `DATABASE.md`, `COMPLIANCE.md`.

Все команды выполняются на VM. Docker Compose вызывается из корня проекта; для
production-профиля указывается файл и профиль (ровно так, как это делает
`ops/vm-autodeploy/deploy.sh`):

```bash
dc() { docker compose --project-directory . -f backend/docker-compose.yml --profile production "$@"; }
```

Репозиторий на VM: `/home/ubuntu/platfoorm_uzassets` (переопределяется `UZA_REPO`).

Контейнеры прод-стека (профиль `production`):

| Контейнер | Образ / сборка | Роль |
|---|---|---|
| `uza-nginx` | сборка `nginx/Dockerfile` (multi-stage: `vite build` фронта + TWA → nginx) | TLS-edge, отдаёт запечённый SPA, reverse-proxy `/api/*` |
| `uza-backend` | сборка `backend/Dockerfile` (uvicorn) | FastAPI, код смонтирован `:ro`, runtime-миграции при старте |
| `uza-postgres` | `postgres:16-alpine` | БД (только внутренняя сеть, порт не публикуется) |
| `uza-tg-bot` | сборка `bot/Dockerfile` | Telegram: polling `telegram_outbox` + обработка MFA-ссылок |
| `uza-backup` | сборка `backend/scripts/backup` (`uza-backup`) | cron pg_dump → gzip → GPG, retention |

Отдельного контейнера фронтенда нет — Vue-бандл и Telegram Mini App запечены в
образ nginx. Отдельного брокера очередей (Redis/RabbitMQ/Celery) в стеке **нет**:
асинхронность обеспечивают FastAPI `BackgroundTasks`, systemd-таймер автодеплоя
и polling-воркер бота, читающий таблицу `telegram_outbox` (`OUTBOX_POLL_SEC=2s`).

## Развёртывание

Модель — **pull-based**: входящий SSH(22) на VM периодически режется фаерволом,
поэтому VM сама тянет `origin/master`. systemd-таймер `uza-autodeploy.timer`
(`OnBootSec=1min`, `OnUnitActiveSec=2min`) запускает `deploy.sh`; если
`origin/master == HEAD`, скрипт выходит без пересборки.

Штатный деплой:

```bash
git push origin master          # через ~2 минуты VM подхватит сама
```

Ручной запуск на VM:

```bash
cd /home/ubuntu/platfoorm_uzassets
bash ops/vm-autodeploy/deploy.sh
```

Что делает `deploy.sh` (`ops/vm-autodeploy/`):
1. сохраняет окруженческий публичный ключ JWT перед `git reset`;
2. `git fetch` + `git reset --hard origin/master`;
3. восстанавливает сохранённый ключ, если reset его затёр;
4. `dc build nginx` + `dc up -d --force-recreate nginx` (пересборка фронта);
5. `dc restart backend` (применяет идемпотентные runtime-миграции и сиды).

Первичная установка таймера — разово через консоль VM: `bash ops/vm-autodeploy/install.sh`
(ставит `uza-autodeploy.service` + `.timer`). Лог деплоя: `/home/ubuntu/uza-autodeploy.log`.

Проверка после деплоя:

```bash
dc ps
git rev-parse --short HEAD                  # задеплоенный коммит
curl -skI https://platform.uz-assets.uz/    # SPA отдаётся
curl -sk  https://platform.uz-assets.uz/api/health   # backend жив → {"status":"ok",...}
```

Правило разделения: фронт запечён в образ nginx → после изменений фронта нужны
`dc build nginx` + `dc up -d --force-recreate nginx`. Backend монтирует код
(`./backend:/app:ro`) → достаточно `dc restart backend`; runtime-миграции
(идемпотентные `ADD COLUMN`) применяются на старте, alembic — для админ-URL.

## Ключи и секреты

Все секреты — в `backend/.env` (в git не входят; в «чистый снимок»
`scripts/make-clean-snapshot.sh` тоже не попадают — вычищает `*.pem`, `*.key`,
`.env`). Ключевые файлы лежат в `backend/keys/` и монтируются в контейнер
`:ro` как `/app/keys/*` (см. `backend/docker-compose.yml`):

- `POSTGRES_PASSWORD` — пароль БД (обязателен, иначе compose падает);
  опционально `APP_DB_USER` / `APP_DB_PASSWORD` — least-privilege роль `uza_app`
  (DML без DDL и без правки `audit_log`); fallback на суперпользователя `uza`;
- JWT RS256 — пара `backend/keys/jwt_private.pem` + `backend/keys/jwt_public.pem`
  (`JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` = `/app/keys/...`); все токены
  обязаны иметь `kid` в header;
- `backend/keys/fernet.key` (`FERNET_KEY_PATH`) — шифрование полей (telegram_chat_id,
  MFA-секреты); плюс `MFA_ENCRYPTION_KEY` в окружении;
- `backend/keys/audit_hmac.key` (`AUDIT_HMAC_SECRET_PATH`) — HMAC-цепочка аудита;
- `AI_API_KEY` (+ `LLM_API_URL`, `LLM_API_VERSION`, `AI_MODEL_*`) — движок ИИ,
  вендор-агностичный; старое имя `ANTHROPIC_API_KEY` работает как fallback;
- `TELEGRAM_BOT_TOKEN`, `BOT_CALLBACK_SECRET`, `TELEGRAM_BOT_USERNAME` — Telegram;
- `SMTP_*` — почта приглашений/уведомлений (если настроена);
- `BACKUP_GPG_RECIPIENT` — email получателя GPG для шифрования бэкапов.

Генерация ключей (готового `scripts/generate-keys.sh` в репозитории **нет** —
использовать команды напрямую):

```bash
# JWT RS256
openssl genrsa -out backend/keys/jwt_private.pem 2048
openssl rsa   -in  backend/keys/jwt_private.pem -pubout -out backend/keys/jwt_public.pem
# Fernet (шифрование полей)
python -c "from cryptography.fernet import Fernet; open('backend/keys/fernet.key','wb').write(Fernet.generate_key())"
# HMAC-секрет аудита
head -c 32 /dev/urandom | base64 > backend/keys/audit_hmac.key
```

`jwt_public.pem` — **окруженческий**: при переносе/reset не затирать чужим, иначе
проверка подписи токенов падает («Signature verification failed») и всех
выбрасывает на логин после MFA. Именно поэтому `deploy.sh` бэкапит и
восстанавливает ключ вокруг `git reset`.

> Расхождение путей (проверять при инцидентах с ключом): canonical-путь ключа —
> `backend/keys/jwt_public.pem` (так его монтирует compose и читает `config.py`),
> а `deploy.sh` сохраняет/восстанавливает `backend/jwt_public.pem`. Если ключ
> лежит только в `backend/keys/`, авто-сейв deploy.sh его не покрывает — при
> проблемах после деплоя проверить оба пути.

## Резервное копирование и восстановление

Копии создаёт контейнер `uza-backup` по cron (`BACKUP_SCHEDULE`, по умолчанию
`0 */6 * * *` — каждые 6 ч; retention `BACKUP_RETENTION_DAYS=30` дней) в томе
`backups`. Конвейер `backup.sh`: `pg_dump` → `gzip -9` → (опц.) GPG-шифрование →
запись SHA-256 в `SHA256SUMS`. Формат архива — `uzassets_<TS>.sql.gz` (или
`.sql.gz.gpg`). По умолчанию `BACKUP_REQUIRE_ENCRYPTION=true`: без валидного
`BACKUP_GPG_RECIPIENT` в keyring бэкап намеренно отказывается писать открытый архив.

Список и ручной прогон:

```bash
docker exec uza-backup ls -lh /backups
docker exec uza-backup cat /backups/SHA256SUMS
docker exec uza-backup /usr/local/bin/backup.sh    # ручной бэкап
```

Восстановление из архива `uza-backup` (plaintext SQL-дамп внутри gzip):

```bash
# 1) остановить backend, чтобы не писал в БД во время restore
dc stop backend
# 2) при GPG: расшифровать (нужен приватный ключ получателя в keyring)
docker exec uza-backup sh -c 'gpg --batch -o /backups/restore.sql.gz -d /backups/<файл>.sql.gz.gpg'
# 3) залить дамп в postgres
docker exec -i uza-postgres sh -c 'gunzip -c' < дамп.sql.gz \
  | docker exec -i uza-postgres psql -U uza -d uzassets
# 4) поднять backend и проверить здоровье
dc up -d backend
curl -sk https://platform.uz-assets.uz/api/health/ready
```

> Локальный dev-клон БД (`pg_dump -Fc` / `pg_restore`, см. INFRASTRUCTURE.md →
> «Клон базы данных») — это отдельный workflow переноса VM→локалка; готового
> файла `database/uzassets.dump` в репозитории **нет** (он не коммитится).

## Наблюдаемость

```bash
dc ps                                      # статусы + health контейнеров
dc logs -f backend                         # логи backend (JSON, LOG_FORMAT=json)
dc logs --since 30m bot                    # логи Telegram-бота
dc logs nginx                              # логи edge-прокси
docker stats --no-stream                   # CPU/RAM по контейнерам
df -h /                                     # диск (на снимке 70%)
free -h ; uptime                            # RAM и load average (на снимке ~10% на 2 ядра)
docker inspect -f '{{.State.Health.Status}}' uza-backend
```

Эндпоинты здоровья backend (`app/api/routes/health.py`, доступны через nginx как
`/api/health*`):

- `GET /api/health` — liveness, всегда 200, без БД;
- `GET /api/health/ready` — readiness, 503 если критичная подсистема деградировала
  или сработал forensic-halt аудита (`app.state.healthy=False`);
- `GET /api/health/components` — детальный статус подсистем (БД, outbox, бот),
  никогда не 503.

Prometheus/Sentry — только если заданы соответствующие переменные окружения.

## Типовые операции

Просмотр данных (postgres слушает только внутреннюю docker-сеть, наружу не открыт):

```bash
docker exec -it uza-postgres psql -U uza -d uzassets -c "\dt"    # список таблиц (~141)
docker exec -it uza-postgres psql -U uza -d uzassets             # интерактив
```

Перезапуск компонентов:

```bash
dc restart backend                  # backend (+ runtime-миграции)
dc build nginx && dc up -d --force-recreate nginx   # nginx после изменений фронта
dc restart bot                      # Telegram-бот
```

## Инциденты

| Симптом | Проверка / действие |
|---|---|
| Сайт не открывается | `dc ps` (nginx up?), `dc logs nginx`; TLS-сертификат не истёк (`backend/scripts/backup/check-ssl-expiry.sh`) |
| API 5xx на роуте | `dc logs backend`; postgres `healthy` (`dc ps`)? миграции применились на старте? проверить трейсбек в JSON-логе |
| «Выброс на логин после MFA» / `Signature verification failed` | `jwt_public.pem` затёрт при деплое/reset — восстановить окруженческий ключ (см. «Ключи»), затем `dc restart backend` |
| Не приходят уведомления Telegram | `dc logs bot`; глубина `telegram_outbox` (`GET /api/health/components`); `TELEGRAM_BOT_TOKEN` задан? |
| Автодеплой не срабатывает | `systemctl status uza-autodeploy.timer`; `/home/ubuntu/uza-autodeploy.log`; исходящий доступ VM к github.com:443 |
| Потеря входящего SSH(22) | это ожидаемо (фаервол режет пакеты) — деплой всё равно идёт pull-моделью через `git push`; не пытаться чинить SSH ради деплоя |
| Нужен откат | `git revert <commit> && git push origin master` — таймер задеплоит откат через ~2 мин (не `reset --hard` на origin) |
| Диск заполняется | `df -h`; размеры томов `postgres_data` / `backups`; retention бэкапов (`BACKUP_RETENTION_DAYS`) |
| Не работает голосовой ввод | серверный заголовок nginx `Permissions-Policy` должен содержать `microphone=(self)` (в шаблоне так и есть) |
| Не работает камера | по умолчанию `camera=()` в `Permissions-Policy` — камера намеренно запрещена; включать только через правку `nginx/templates/default.conf.template` |

## Гейты качества (перед деплоем)

```bash
# backend
python -m py_compile <изменённые модули>
pytest                       # тесты на testcontainers (схема через Base.metadata.create_all + seed)
# frontend
cd frontend && npx vite build   # эталонная прод-сборка (так же строит nginx-образ); exit 0
```

`npm run build` / `vue-tsc -b` падают на пред-существующих type-ошибках —
эталонный гейт фронта именно `npx vite build`.

## Изменения с прошлого снимка (2026-07-20 → 2026-07-21)

Эксплуатационно значимое из c9f29f3:

- **RBAC-упрочнение**: privilege-ceiling на всех путях выдачи прав/ролей
  (helpers `_ensure_group_membership_within_ceiling` /
  `_ensure_assigned_scope_within_ceiling` в `services/rbac_v3/service.py`) —
  закрыта вертикальная и горизонтальная (per-company/sector) самоэскалация.
  `PATCH /me` self-set `organization_id` теперь валидирует существование
  компании и пишет аудит-запись.
- **AI-чат**: убран 400 на моделях без `temperature` (Opus) — авто-heal
  (`payload.pop("temperature")` при 400) в `services/ai_service.py`, в т.ч. в
  стриминговом пути.
- **Честность метрик** (на расчёты, не на эксплуатацию): единый предикат
  «план утверждён» в forensic, governance-KPI по факту заседаний, живой курс
  USD в обзоре, «—» вместо ложного `0.00×` для Debt/EBITDA.
- **Удаление мёртвого кода**: локальные Vue-модули FinModel / Credit Portfolio /
  Invest Projects (роуты стали render-null с прежним внешним редиректом на
  `dashboard.uz-assets.uz`), FinModelUapV1, часть ExecDash-блоков. Backend
  `credit_scenario` и `invest_projects` — **живые** (используются CreditNagruzkaTab
  в `/system-config` и ExecDash), не тронуты.

Диаграммы: `docs/handoff/diagrams/c4_container.png`, `c4_context.png`,
`infrastructure.png`.
