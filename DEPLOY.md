# UzAssets — деплой на UzTelecom Cloud (uzcloud.uz)

> Это пошаговый чек-лист **для тебя как оператора**. Всё что можно было
> сделать в коде — уже сделано:
> - Backend Dockerfile имеет entrypoint, который сам прогоняет `alembic upgrade head`
> - Nginx Dockerfile параметризован через `${BACKEND_HOST}` / `${BACKEND_PORT}`
> - GitHub Actions автоматически собирает образы и пушит в GHCR
> - `.env.production.example` лежит в корне со списком всех необходимых vars

---

## Шаг 0 — Один раз перед деплоем (15 минут)

### 0.1. Сгенерируй секреты локально

```powershell
# JWT keypair (RS256, 2048-bit)
cd backend/keys
openssl genrsa -out jwt_private.pem 2048
openssl rsa  -in jwt_private.pem -pubout -out jwt_public.pem

# Fernet key (32 bytes base64url, для encryption.py)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > fernet.key

# Audit HMAC secret (32 bytes hex)
python -c "import secrets; print(secrets.token_hex(32))" > audit_hmac.key

# MFA encryption key (для .env, не файл — base64 32 bytes)
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
# Скопируй вывод в MFA_ENCRYPTION_KEY ниже.

# Bot callback HMAC
python -c "import secrets; print(secrets.token_hex(32))"
# Скопируй в BOT_CALLBACK_SECRET.
```

### 0.2. Заполни env-vars в текстовом файле

Скопируй `.env.production.example` в `.env.production.uzcloud` (НЕ коммитить!) и заполни. Эти значения будешь вбивать в uzcloud UI.

### 0.3. Подключи Push в GHCR (если используем Docker Registry путь)

Workflow `.github/workflows/build-and-push.yml` уже создан. После того как закоммитишь и запушишь — на каждый push в master GitHub автоматически собирает 3 образа и пушит в:

```
ghcr.io/vladkimvl-uza/uzassets-backend:latest
ghcr.io/vladkimvl-uza/uzassets-nginx:latest
ghcr.io/vladkimvl-uza/uzassets-bot:latest
```

После первого push'а проверь в GitHub Actions tab что workflow зелёный, и в `Packages` (правое меню в репо) что 3 образа появились.

**По умолчанию** GHCR-packages приватные. Сделай их публичными (чтобы uzcloud мог тянуть без аутентификации) или создай PAT (Personal Access Token) с `read:packages` и сохрани в uzcloud Registry Credentials.

---

## Шаг 1 — DNS (5 минут)

В DNS-провайдере (где зарегистрирован `uz-assets.uz`) добавь:

```
A   platform.uz-assets.uz   →   <public IP nginx-app из uzcloud>
```

Public IP появится после создания nginx-app на Шаге 4. Можно сначала пройти Шаг 4, узнать IP, потом вернуться.

---

## Шаг 2 — Postgres app в uzcloud

**Платформа приложений → Создать приложение → Docker registry**

| Поле | Значение |
|---|---|
| Image | `postgres:16-alpine` |
| Имя App | `postgres-app` |
| Internal port | `5432` |
| Publish externally | НЕТ |
| Env vars | `POSTGRES_USER=uza`<br>`POSTGRES_PASSWORD=<сгенерированный>`<br>`POSTGRES_DB=uzassets`<br>`PGDATA=/var/lib/postgresql/data/pgdata` |
| Persistent volume | `/var/lib/postgresql/data` → 20 GB SSD |
| CPU / RAM | 1 CPU / 1 GB (минимум) |

Запиши internal hostname (`postgres-app.<cluster>.svc.cluster.local` или просто `postgres-app`).

---

## Шаг 3 — Backend app

**Платформа приложений → Создать приложение → Github** → `vladkimvl-uza/platfoorm_uzassets` → ветка `master`.

| Поле | Значение |
|---|---|
| Имя App | `backend-app` |
| Dockerfile path | `backend/Dockerfile` |
| Build context | `backend` |
| Internal port | `8000` |
| Publish externally | НЕТ (только через nginx) |
| CPU / RAM | 2 CPU / 2 GB |

### Env vars

Скопируй из `.env.production.example` (секция BACKEND-APP), заменив плейсхолдеры. Минимум:

- `DATABASE_URL`, `DATABASE_URL_SYNC`, `DATABASE_URL_ADMIN`
- Все `JWT_*`
- `FERNET_KEY_PATH`, `AUDIT_HMAC_SECRET_PATH`, `MFA_ENCRYPTION_KEY`
- `TRUSTED_HOSTS=platform.uz-assets.uz,backend-app,nginx-app,localhost`
- `CORS_ORIGINS=https://platform.uz-assets.uz`
- `FORCE_HTTPS=true`
- `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `BOT_CALLBACK_SECRET`
- `RUN_MIGRATIONS=1`

### Secret volumes

| Mount path | Содержимое |
|---|---|
| `/app/keys/jwt_private.pem` | содержимое локального `backend/keys/jwt_private.pem` |
| `/app/keys/jwt_public.pem`  | то же `jwt_public.pem` |
| `/app/keys/fernet.key`      | то же `fernet.key` |
| `/app/keys/audit_hmac.key`  | то же `audit_hmac.key` |

В uzcloud это делается через «Secrets» или «Files» в UI приложения. Каждый файл — отдельная запись.

### Persistent volume

| Mount path | Размер |
|---|---|
| `/app/uploads` | 10 GB |

---

## Шаг 4 — Nginx app

**Платформа приложений → Создать приложение → Github** → тот же репо.

| Поле | Значение |
|---|---|
| Имя App | `nginx-app` |
| Dockerfile path | `nginx/Dockerfile` |
| Build context | `.` ← **корень репо, не nginx/** |
| Internal port | `80`, `443` |
| Publish externally | **ДА** на 443 |
| CPU / RAM | 0.5 CPU / 512 MB |

### Env vars

```
BACKEND_HOST=backend-app
BACKEND_PORT=8000
```

### Домен и TLS

В разделе nginx-app → Domains → добавь `platform.uz-assets.uz` → включи Let's Encrypt.

UzCloud сам выдаст cert, примонтирует и подменит пути. Если нужно вручную править — в `nginx/templates/default.conf.template` есть строки:

```nginx
ssl_certificate     /etc/nginx/certs/dev-fullchain.pem;
ssl_certificate_key /etc/nginx/certs/dev-privkey.pem;
```

Замени пути на те, что использует uzcloud (обычно `/etc/letsencrypt/live/<domain>/fullchain.pem`).

**Сборка займёт ~5 минут** в первый раз (frontend `vite build` + twa `vite build` + brotli-builder `make modules`). На последующих push'ах GHA-cache ускоряет до ~2 мин.

### Получи public IP nginx-app

В разделе nginx-app → Network. Скопируй public IP → обнови DNS A-запись для `platform.uz-assets.uz` (Шаг 1).

---

## Шаг 5 — Bot app (опционально)

**Платформа приложений → Создать приложение → Github**

| Поле | Значение |
|---|---|
| Имя App | `bot-app` |
| Dockerfile path | `bot/Dockerfile` |
| Build context | `bot` |
| Publish externally | НЕТ (бот сам ходит к Telegram API) |
| CPU / RAM | 0.25 CPU / 256 MB |

### Env vars

```
TELEGRAM_BOT_TOKEN=<тот же что в backend>
DATABASE_URL=postgresql+asyncpg://...@postgres-app:5432/uzassets
BACKEND_BASE_URL=http://backend-app:8000
BOT_CALLBACK_SECRET=<тот же что в backend>
PLATFORM_URL=https://platform.uz-assets.uz
```

---

## Шаг 6 — Проверка

После того как все 4 App'a в статусе **Running**:

```bash
# С локальной машины:
curl -I https://platform.uz-assets.uz/api/health
# Ожидаем: HTTP/2 200

curl -I https://platform.uz-assets.uz/
# Ожидаем: HTTP/2 200, content-type: text/html

curl -I https://platform.uz-assets.uz/twa/
# Ожидаем: HTTP/2 200

# Проверка brotli:
curl -sI -H 'Accept-Encoding: br' https://platform.uz-assets.uz/assets/vue-vendor-*.js | grep encoding
# Ожидаем: content-encoding: br

# Проверка миграций (через uzcloud веб-shell в backend-app):
alembic current
# Должна быть последняя alembic версия из репо
```

---

## Что делать если что-то ломается

| Симптом | Где смотреть |
|---|---|
| nginx-app: `502 Bad Gateway` | logs nginx-app → проверь `BACKEND_HOST` env var |
| backend-app: `400 Invalid host header` | env `TRUSTED_HOSTS` — там должен быть `platform.uz-assets.uz` |
| backend-app: crash при старте | logs → ищи `alembic` ошибки. Может не быть прав DDL у `uza_app` user — используй `uza` superuser в `DATABASE_URL_ADMIN` |
| `/auth/login`: 500 | проверь mount `/app/keys/jwt_*.pem` — файлы должны быть читаемы и валидны |
| TLS cert не выдан | DNS не указывает на nginx-app public IP / порт 80 не открыт наружу для ACME challenge |
| Build падает на vue-tsc | мы убрали `vue-tsc -b` из Dockerfile, должен использоваться `npx vite build` напрямую. Проверь Dockerfile в репо. |
| Долгий build | первый раз ~5 мин (brotli + 2 vite builds). На последующих push'ах ~2 мин благодаря GHA-cache. |

---

## Обновление после первого деплоя

1. Закоммитил изменения, запушил в master.
2. GitHub Actions автоматически собрал и запушил образы в GHCR.
3. В uzcloud каждого App'a — «Redeploy» (если был Github-режим) или «Pull latest image» (Docker Registry режим).
4. Если поменялись миграции — entrypoint их применит при старте backend-app.

---

## Связанные файлы

- `.env.production.example` — список всех env vars
- `.github/workflows/build-and-push.yml` — auto-build в GHCR
- `backend/docker-entrypoint.sh` — миграции на старте
- `nginx/templates/default.conf.template` — параметризованный nginx config
- `nginx/Dockerfile` — multi-stage с brotli modules
