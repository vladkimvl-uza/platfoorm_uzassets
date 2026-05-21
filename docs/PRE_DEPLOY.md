# Pre-Deploy Checklist — Pack 145 / 146

Применяется при переходе с любой версии **до** RBAC-консолидации на текущий master (commit `daa332d` или новее).

Изменения, влияющие на деплой:
- RBAC v1+v2 удалены, всё переехало в `/rbac/v3/*`.
- 5 таблиц БД дропаются миграцией `9aC_drop_rbac_v2_unused`.
- JWT теперь обязан иметь `kid` в header — старые токены без него → 401.
- Group permission grants начали реально применяться на endpoint-уровне (раньше игнорировались).
- Hard-coded backdoor `if email == "v.kim@uz-assets.uz": grant all` удалён из bp/kpi.
- Frontend ходит в `/rbac/v3/*` и `/rbac/v3/groups/*` вместо `/rbac/*` и `/rbac/v2/groups/*`.

---

## 0. Pre-flight — за день до деплоя

- [ ] **CI зелёный** на master: `https://github.com/vladkimvl-uza/platfoorm_uzassets/actions` — pytest 123 passed.
- [ ] **Бэкап БД** свежий (≤24 ч). `pg_dump --format=custom` всего dataset'а + отдельно `audit_log` (он самый ценный из-за HMAC-цепочки).
- [ ] **Бэкап `backend/keys/`** на надёжный носитель: `jwt_private.pem`, `fernet.key`, `audit_hmac.key`. Без них refresh-токены и audit-цепочка не восстановятся.
- [ ] **Согласуй окно низкой активности** (15-30 мин). Все юзеры с активным JWT access (≤30 мин TTL) и refresh (≤14 дней TTL) могут получить 401 в момент перехода.
- [ ] **Объяви пользователям** что после деплоя возможно потребуется перелогиниться один раз.
- [ ] **Проверь что в проде НЕТ юзера с email `v.kim@uz-assets.uz`** который полагается на email-backdoor. Если такой есть — выдай ему явно role `admin` ДО деплоя, иначе он потеряет права.
- [ ] **Проверь существующие `group_permission_grant` записи в проде:**
  ```sql
  SELECT g.code, gpg.permission_code, gpg.grant_type
  FROM group_permission_grant gpg
  JOIN groups g ON g.id = gpg.group_id
  ORDER BY g.code, gpg.permission_code;
  ```
  Раньше эти grants/denies **молча игнорировались**. После деплоя они начнут реально применяться — может неожиданно зарезать кому-то доступ или, наоборот, дать лишний. Просмотри список с админом RBAC.

## 1. Deploy

### 1.1. Pull & build
```bash
git fetch origin
git checkout master
git pull --ff-only
```

### 1.2. Backend: миграция БД (необратимо)

```bash
docker compose exec backend alembic current   # запиши текущую head
docker compose exec backend alembic upgrade head
```

Накатываются миграции (с момента 9aA вверх):
- `9aA_telegram_2fa` (если ещё не накатана)
- `9aB_mfa_onboarding`
- **`9aC_drop_rbac_v2_unused`** — DROP TABLE: `user_permission_grant`, `user_module_visibility`, `permission_template`, `group_role`, `rbac_change_log`. ⚠ Данные в этих таблицах теряются безвозвратно (downgrade — no-op).

После накатывания:
```bash
docker compose exec backend alembic current   # должно показать 9aC_drop_rbac_v2_unused
```

### 1.3. Backend: redeploy
```bash
docker compose up -d --build backend
docker compose logs -f backend --tail=80
```

Жди строки `Routers: 42 mounted, 1 skipped` — это сигнал что app поднялся.

В логах ищи `rbac_v3` (новый), НЕ должен видеть `rbac` или `rbac_v2` в строках `[OK] app.api.routes.<name>`.

### 1.4. Frontend: redeploy
```bash
docker compose up -d --build frontend
# или, если фронт собирается отдельно:
cd frontend && npm ci && npm run build
```

Frontend теперь делает запросы на:
- `/rbac/v3/users`, `/rbac/v3/roles`, `/rbac/v3/groups`, `/rbac/v3/role-by-email`, `/rbac/v3/users/{id}/preview-token`
Старые `/rbac/users`, `/rbac/v2/groups/*` больше не существуют — старый фронт получит 404.

---

## 2. Post-deploy smoke

### 2.1. API liveness
```bash
curl -s https://platform.uz-assets.uz/api/__alive__
# {"status":"ok"}

curl -s https://platform.uz-assets.uz/api/
# {..., "routers_mounted": 42, "routers_skipped": 1}
```

### 2.2. RBAC v3 endpoints
Авторизуйся в UI (или получи токен через `/auth/login`), затем:
```bash
TOKEN=...
curl -s -H "Authorization: Bearer $TOKEN" https://platform.uz-assets.uz/api/rbac/v3/users | head -c 200
curl -s -H "Authorization: Bearer $TOKEN" https://platform.uz-assets.uz/api/rbac/v3/roles | head -c 200
curl -s -H "Authorization: Bearer $TOKEN" https://platform.uz-assets.uz/api/rbac/v3/overview | head -c 200
```
Все три — 200 OK с непустым JSON.

### 2.3. Старые пути отдают 404
```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" \
  https://platform.uz-assets.uz/api/rbac/users
# 404
```

### 2.4. JWT kid enforced
```bash
# Свежий токен — должен работать
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" \
  https://platform.uz-assets.uz/api/rbac/v3/overview
# 200
```
Старые токены до деплоя (если их сохранили) — должны вернуть 401 с `"Missing kid in JWT header"`.

### 2.5. Group permissions реально применяются
Если в `group_permission_grant` есть deny-записи для какого-то юзера на `kpi.view`:
```bash
# От имени этого юзера запросить /kpi/summary/2026/year — ожидаем 403
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $USER_TOKEN" \
  https://platform.uz-assets.uz/api/kpi/summary/2026/year
# 403
```
Если до деплоя возвращалось 200 (deny игнорировался) — это и есть фикс C1.

### 2.6. invest_projects namespace
Любой scoped юзер должен получать 403 на root:
```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $USER_TOKEN" \
  https://platform.uz-assets.uz/api/invest-projects-storage/root/
# 403 для не-admin
```

### 2.7. Frontend UI sanity
- [ ] Открой `/admin/rbac-v3` — список юзеров, ролей, групп загружается.
- [ ] Открой страницу одной из portfolio-компаний (KPI / BP) — данные грузятся.
- [ ] Создай тестовую запись (заметку или KPI cell) — успех.
- [ ] Через DevTools Network убедись что нет запросов на `/rbac/users` или `/rbac/v2/*` (только `/rbac/v3/*`).

---

## 3. Если что-то сломалось — rollback

### 3.1. Backend / frontend
```bash
git checkout <previous-tag-or-commit>
docker compose up -d --build backend frontend
```

### 3.2. Миграция (необратимо для данных)
Миграция `9aC_drop_rbac_v2_unused` имеет `downgrade()` = no-op (таблицы удалены без бэкапа схемы). Если нужно вернуть таблицы:
1. Восстанови БД из бэкапа от шага 0.
2. Накати все миграции до 9aB (не включая 9aC).

### 3.3. Старые JWT перестали работать
Это by design (kid обязателен). Юзеры должны перелогиниться. Если массовая проблема:
- Временно убери проверку kid (закомментируй блок в `app/core/jwt.py:143-149`) и redeploy backend.
- Дай юзерам сутки на естественное истечение access-токенов.
- Верни проверку kid обратно.

### 3.4. Group permissions неожиданно зарезали доступ
Удалить проблемный grant:
```sql
DELETE FROM group_permission_grant
WHERE permission_code = '<problematic>' AND grant_type = 'deny';
```
Или временно promote юзера в `admin` role.

---

## 4. Контакты / эскалация

- Owner platform: `v.kim@uz-assets.uz`
- Git remote: https://github.com/vladkimvl-uza/platfoorm_uzassets
- Аудит-цепочка: `audit_log` table (HMAC-chained, не редактируется).

## 5. Готовые SQL-проверки для шага 0

```sql
-- Сколько group permission grants реально записаны
SELECT COUNT(*), grant_type FROM group_permission_grant GROUP BY grant_type;

-- Сколько активных юзеров с role 'admin'
SELECT COUNT(DISTINCT u.id) FROM users u
JOIN user_role ur ON ur.user_id = u.id
JOIN roles r ON r.id = ur.role_id
WHERE r.code = 'admin' AND u.is_active;
-- Должно быть >= 1 (иначе after deploy некому будет управлять RBAC)

-- Существует ли legacy hardcoded backdoor account
SELECT id, email, is_owner, is_active FROM users
WHERE email ILIKE 'v.kim@uz-assets.uz';
-- Если is_owner=false и не имеет 'admin' role — нужно выдать перед деплоем
```

---

# Pre-Deploy — Security Hardening Pack (Pack 148)

Применяется поверх Pack 145/146. Добавляет: secret rotation, CORS-defaults, audit-chain coverage, MFA backoff, concurrent-session cap, IP allowlist enforcement, container hardening, backup encryption, password expiry policy, observability instrumentation, DB user separation.

## A. Pre-flight (за день до)

- [ ] Резервная копия `audit_log` отдельно (rebuild чейна делается с `LOCK TABLE ACCESS EXCLUSIVE` — секундный downtime записи; safety net на случай отката).
- [ ] Резервная копия `backend/keys/` — `jwt_*.pem`, `fernet.key`, `audit_hmac.key`.
- [ ] Записать чексумму текущего chain head:
  ```sql
  SELECT entry_hash FROM audit_log ORDER BY created_at DESC LIMIT 1;
  ```
- [ ] Сгенерировать новые DB-пароли (см. §C ниже).
- [ ] Сгенерировать новый SENTRY_DSN если включаешь error tracking.

## B. Configuration changes

### B.1. Production uvicorn command (no `--reload`)

В `.env` или compose override:

```bash
COMPOSE_BACKEND_CMD='uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips=172.16.0.0/12,10.0.0.0/8'
```

- `--reload` НЕ должно быть в production. Файл-watcher subprocess — лишний вектор атаки + потребляет inotify.
- `--workers 4` (или по числу CPU) — utilize CPU и параллелит bcrypt.
- `--proxy-headers --forwarded-allow-ips` ограничивает trusted hops nginx CIDR (Docker bridge).

### B.2. Disable interactive docs in production

Default — `/docs`, `/redoc`, `/openapi.json` отключены если `ENVIRONMENT=production`.
Если нужны для staging — `ENABLE_DOCS_IN_PRODUCTION=true`.

### B.3. CORS strict origins

`.env` должен содержать **явный** список:

```bash
CORS_ORIGINS=https://platform.uz-assets.uz,https://app.uz-assets.uz
```

Default теперь `[]` (deny-all). Wildcard `*` с `allow_credentials=True` в prod вызовет FATAL на startup.

### B.4. Rate limit trusted proxies

```bash
RATE_LIMIT_TRUSTED_PROXIES=172.16.0.0/12,10.0.0.0/8,127.0.0.0/8
```

Если nginx находится в другой сети — добавь его CIDR. Без этого rate limit будет считать nginx как обычного клиента и легко bypass'нется любым клиентом (все запросы идут через nginx → одна ключ-корзина).

### B.5. Backup encryption (mandatory)

```bash
BACKUP_REQUIRE_ENCRYPTION=true            # default
BACKUP_GPG_RECIPIENT=ops@uz-assets.uz     # email с импортированным public key
```

Import public key into backup container's keyring до первого запуска:
```bash
docker compose exec backup gpg --import < /path/to/ops-public.asc
```

Без recipient'а с импортированным ключом — backup container будет fail-fast на старте.

## C. DB user separation (P1-7)

Новые роли с минимальными привилегиями. Текущий `uza` остаётся как admin/migrations user.

### C.1. Создать роли в БД (one-time)

```bash
# Generate strong passwords (32 chars, random)
export APP_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
export BACKUP_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)

# Сохрани эти значения — потом положишь в .env
echo "APP_DB_PASSWORD=$APP_DB_PASSWORD"     # → .env
echo "BACKUP_DB_PASSWORD=$BACKUP_DB_PASSWORD"  # → .env

# Apply role grants (idempotent — re-run для ротации паролей)
docker cp backend/scripts/setup-db-users.sql uza-postgres:/tmp/
docker exec -e PGPASSWORD=$POSTGRES_PASSWORD \
  -e APW="$APP_DB_PASSWORD" -e BPW="$BACKUP_DB_PASSWORD" uza-postgres \
  bash -c 'psql -U uza -d uzassets -v ON_ERROR_STOP=1 \
       -v app_password="$APW" \
       -v backup_password="$BPW" \
       -v app_db="uzassets" \
       -f /tmp/setup-db-users.sql'
```

### C.2. Переключить backend на `uza_app`

```bash
# .env
APP_DB_USER=uza_app
APP_DB_PASSWORD=<сохранённый выше>

# Recreate backend container с новой DATABASE_URL
docker compose up -d --force-recreate backend
docker compose logs backend --tail 30   # убедись что connect OK
```

### C.3. Переключить backup на `uza_backup`

```bash
# .env
BACKUP_DB_USER=uza_backup
BACKUP_DB_PASSWORD=<сохранённый выше>

docker compose --profile production up -d --force-recreate backup
```

### C.4. Verify

```bash
# Backend не должен иметь DROP/DDL прав
docker exec -e PGPASSWORD=$APP_DB_PASSWORD uza-postgres psql -U uza_app -d uzassets \
  -c "DROP TABLE users;"   # ERROR: must be owner

# Backend не может UPDATE/DELETE audit_log
docker exec -e PGPASSWORD=$APP_DB_PASSWORD uza-postgres psql -U uza_app -d uzassets \
  -c "DELETE FROM audit_log;"   # ERROR: permission denied

# Backup может SELECT
docker exec -e PGPASSWORD=$BACKUP_DB_PASSWORD uza-postgres psql -U uza_backup -d uzassets \
  -c "SELECT count(*) FROM audit_log;"   # OK

# Backup не может INSERT
docker exec -e PGPASSWORD=$BACKUP_DB_PASSWORD uza-postgres psql -U uza_backup -d uzassets \
  -c "INSERT INTO users (email, password_hash, full_name) VALUES ('x','x','x');"
  # ERROR: permission denied
```

### C.5. Rollback (если что-то сломалось)

В `.env` удалить `APP_DB_*` и `BACKUP_DB_*` — fallback к `uza` superuser автоматически. Re-create.

## D. Audit chain — post-deploy verification

```bash
docker exec uza-backend sh -c 'cd /app && python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.core.audit_chain import verify_chain
async def main():
    async with AsyncSessionLocal() as db:
        res = await verify_chain(db)
        print(res)
asyncio.run(main())
"'
# Ожидается: {'checked': <N>, 'ok': True, 'broken_at': None}
```

UNIQUE constraint `uq_audit_log_prev_hash` теперь защищает от race-conditions. Background task (hourly) автоматически verify'ит чейн и log'ает ERROR при поломке.

## E. Observability (опционально)

```bash
# .env
SENTRY_DSN=https://<key>@sentry.io/<project>
SENTRY_TRACES_SAMPLE_RATE=0.1
PROMETHEUS_ENABLED=true
```

Sentry: PII scrubbing уже включён, email редактируется в before_send.
Prometheus: `/metrics` endpoint требует Bearer auth с `metrics.read` permission (защита от scraping публики).

## F. Frontend rebuild

Если меняешь password policy length (128 → ?), убедись что frontend `ChangePasswordPage.vue` валидирует тот же лимит.

```bash
docker exec uza-frontend sh -c "rm -rf /app/dist /app/node_modules/.vite"
docker exec -e NODE_OPTIONS=--max-old-space-size=4096 -e VITE_API_BASE_URL= \
  uza-frontend npx vite build
docker restart uza-frontend
```

## G. Post-deploy smoke

- [ ] `/health` → 200
- [ ] `/openapi.json` → 404 если ENVIRONMENT=production (правильно, скрыт)
- [ ] Login существующим юзером с обычным паролем → 200, JWT issued
- [ ] Login с устаревшим паролем (>90 дн) → next request returns 403 password_change_required
- [ ] `/change-password` page загружается
- [ ] Wrong password 5 раз → MFA brute-force backoff активируется
- [ ] Запустить >5 параллельных login для одного юзера → старые sessions revoked
- [ ] Audit chain verify → OK
- [ ] Backup run manually (`docker exec uza-backup /usr/local/bin/backup.sh`) → encrypted .gpg file
- [ ] SSL cert check (`docker exec uza-backup /usr/local/bin/check-ssl-expiry.sh`) → OK или WARN если ≤30 дней
- [ ] nginx access log: подтверди что `access_token=` редактируется в `[REDACTED]`

## H. Rollback plan

1. `git revert <commit>` — но миграции БД (audit chain rebuild, UNIQUE constraint) необратимы без бэкапа audit_log
2. `docker compose up -d --force-recreate backend frontend` — старый код вернётся
3. Для отката DB user separation: `.env` без APP_DB_*/BACKUP_DB_*, recreate — fallback к superuser работает
4. Audit chain поломан после revert? — rebuild scripts/chain_rebuild.py с прежним recipe (см. git log)

