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
