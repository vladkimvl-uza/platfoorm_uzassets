# Информационная безопасность — базовый каркас

> Уровень: базовые требования госуровня. Документ — карта реализованных контролей и того, что добавляется в последующих частях.

Платформа размещает данные 22 портфельных компаний (государственные активы Узбекистана). Соответственно, applied baseline ≈ ИСПДн-2 / ГИС-1 в терминах ФСТЭК (Россия) или эквивалент по O‘zDSt 1092/27001-аналогам. В деплое — data sovereignty (uzcloud.uz, Coolify).

---

## 1. Идентификация и аутентификация

| Контроль | Реализация | Где |
|---|---|---|
| Локальная аутентификация (без внешнего IdP) | Username/email + пароль | Часть 2 |
| Хэш паролей: bcrypt cost 12 | `app/core/password.py` | ✅ |
| Минимальная длина 12 + требование классов символов | `validate_password_policy()` | ✅ |
| История паролей (no-reuse последних 5) | `User.password_history` JSONB + `check_password_history()` | ✅ |
| Принудительная ротация (90 дней) | `password_changed_at` + `must_change_password` | Часть 2 (auth/me) |
| Lockout после 5 неудач на 30 минут | `failed_login_attempts` + `locked_until` | Часть 2 |
| MFA / TOTP (опционально для admin/owner/cfo_*) | `mfa_enabled`, `mfa_secret_encrypted` (Fernet) | Часть 2 |
| Тайм-аут idle сессии (30 мин) и абсолютной (12 ч) | `SESSION_IDLE_TIMEOUT_MINUTES`, `SESSION_ABSOLUTE_TIMEOUT_HOURS` | Часть 2 |
| Чёрный список распространённых паролей | `_COMMON_PASSWORDS` (расширяется) | ✅ |

## 2. Авторизация (RBAC)

| Контроль | Реализация |
|---|---|
| 22 платформенные роли с категорией и `approval_level` | таблица `roles`, заполнено в `0001_initial` |
| Каталог permissions с кодом и модулем | таблица `permissions` |
| Связь many-to-many `role_permission`, `user_role` | ✅ |
| Per-organization scope для `organization` | `User.organization_id` |
| Per-department scope для иерархии одобрения | `User.department`, `User.supervisor_id` |
| `require_permission(code)` dependency | Часть 2 |
| `require_role(...)` dependency | Часть 2 |
| Audit-only `audit_viewer` (read-only во всех `*.view`) | Часть 2 (матрица ролей) |

## 3. Криптография

| Контроль | Реализация |
|---|---|
| TLS 1.2+ only на edge | nginx: `ssl_protocols TLSv1.2 TLSv1.3` |
| Strong ciphers (X25519, P-384, AES-GCM, ChaCha20-Poly1305) | nginx config |
| HSTS 1 год + preload | `Strict-Transport-Security` в nginx и в `SecurityHeadersMiddleware` |
| JWT на RS256 (асимметричная подпись) | `app/core/jwt.py`, ключи RSA-3072 |
| Field-level encryption (Fernet AES-128-CBC + HMAC-SHA256) | `app/core/encryption.py`, `MultiFernet` для ротации |
| Audit log integrity (HMAC-SHA256 цепочка) | `app/core/audit_chain.py`, `prev_hash` + `entry_hash` |
| Без MD5/SHA1/DES/3DES в коде | соблюдается |

## 4. Сетевая безопасность / edge

| Контроль | Реализация |
|---|---|
| HTTP→HTTPS редирект | nginx `server { listen 80 ... return 301 https://...; }` |
| Postgres internal-only (нет proxy на хост) | `expose: 5432` без `ports` в `docker-compose.yml` |
| Trusted-Host middleware | FastAPI `TrustedHostMiddleware` + `TRUSTED_HOSTS` |
| Строгая CORS-политика | whitelisted origins, methods, headers; `max_age=600` |
| Лимиты тела запроса | `BodySizeLimitMiddleware` + nginx `client_max_body_size 25m` |
| Лимит коннектов с одного IP | nginx `limit_conn conn_per_ip 50` |
| Rate limit auth: 10/min | nginx `auth_zone` + slowapi `RATE_LIMIT_AUTH` |
| Rate limit API: 300/min | nginx `api_zone` + slowapi `RATE_LIMIT_API` |
| Rate limit heavy (reports/AI): 30/min | nginx `heavy_zone` + slowapi `RATE_LIMIT_HEAVY` |
| Скрытие версии сервера | nginx `server_tokens off` + удаление `Server` хедера в middleware |
| Блок прощупывания (`/.git`, `.env`, `.php`) | nginx location + `deny all` |

## 5. Заголовки безопасности

Применяются и на nginx, и в FastAPI (`SecurityHeadersMiddleware`) — defense in depth:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Cross-Origin-Opener-Policy: same-origin`
- `Cross-Origin-Resource-Policy: same-site`
- `X-Permitted-Cross-Domain-Policies: none`
- `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), microphone=(), payment=(), usb=()`
- `Content-Security-Policy` (production-режим: `default-src 'self'; script-src 'self'; frame-ancestors 'none'; object-src 'none'`)
- На `/auth/*` и `/admin/*`: `Cache-Control: no-store, no-cache, must-revalidate, private`

## 6. Аудит и логирование

| Контроль | Реализация |
|---|---|
| Append-only `audit_log` | модель + миграция `0001_initial` |
| HMAC-цепочка целостности | `prev_hash`, `entry_hash`, секрет в `/app/keys/audit_hmac.key` |
| Команда верификации цепочки | `verify_chain()` в `app/core/audit_chain.py` |
| Ретенция 5 лет | `AUDIT_RETENTION_DAYS=1825` |
| JSON-логи в stdout | `app/core/logging.py` (`JsonFormatter`) |
| PII-редактирование | `redact()` — пароли, токены, hashes, cookies, bcrypt-хэши, JWT |
| Correlation ID (`X-Request-ID`) | `RequestIDMiddleware`, проксируется на бэкенд |
| Аудит логин-событий (success/fail/lockout) | Часть 2 |
| Аудит изменений данных (create/update/delete) | за модулем — Части 5–10 |

## 7. Управление секретами

| Файл | Содержимое | Доступ |
|---|---|---|
| `backend/keys/jwt_private.pem` | RSA-3072 приватный | `chmod 600`, mounted read-only в backend |
| `backend/keys/jwt_public.pem` | RSA-3072 публичный | `chmod 644` |
| `backend/keys/fernet.key` | Fernet master key | `chmod 600` |
| `backend/keys/audit_hmac.key` | 64 байта HMAC-секрет | `chmod 600` |
| `nginx/certs/dev-{fullchain,privkey}.pem` | Self-signed dev TLS | `chmod 600` private |

Генерация: `bash scripts/generate-keys.sh`. В продакшене ключи управляются вне репозитория (KMS / Hashicorp Vault / переменные окружения Coolify). `.gitignore` исключает `backend/keys/` и `nginx/certs/`.

Ротация:
- JWT keypair — `Multi-Fernet`-style с `kid`, новый в начало списка, старый держим для верификации до истечения всех refresh-токенов
- Fernet master key — `MultiFernet([new, old, ...])`, `cryptography` сама расшифрует старым и зашифрует новым при перезаписи
- HMAC аудита — НЕ ротируется без re-signing цепочки; раз в год добавляется новый секрет с записью события в audit_log

## 8. Резервное копирование

| Контроль | Реализация |
|---|---|
| `pg_dump` каждые 6 часов | `scripts/backup/backup.sh` + cron в контейнере `uza-backup` |
| Сжатие на лету (никогда не лежит без gzip) | pipe `pg_dump | gzip --best > .tmp` → `mv` |
| Опциональное GPG-шифрование | `BACKUP_GPG_RECIPIENT` |
| SHA-256 манифест | `SHA256SUMS` рядом с архивом |
| Ретенция 30 дней | `BACKUP_RETENTION_DAYS` |
| Том отделён от data-volume | `postgres_backups` отдельный |
| Запускается только в `production` profile | избегаем шума в dev |

В продакшене дополнительно: репликация в S3 / Object Storage uzcloud.uz, DR-сайт с PITR.

## 9. Защита приложения (OWASP)

| Класс | Защита |
|---|---|
| SQL injection | SQLAlchemy 2.0 параметризация — везде; никаких `f"SELECT ... {x}"` |
| XSS | Vue 3 экранирование по умолчанию; `v-html` запрещён в code review |
| CSRF | API — JWT в `Authorization: Bearer`, не cookies → CSRF не применим. Если в будущем Cookie-Auth — добавить `SameSite=Strict` + double-submit token |
| Open redirect | Запрет `Location` с внешним хостом в `/auth/*` |
| Mass assignment | Pydantic-схемы белый-список полей |
| Path traversal | Все path-параметры — UUID; uploads через `python-multipart` валидируются |
| Server-side request forgery | Allowlist для исходящих HTTP (Anthropic API только) |
| Dependency vulns | `pip-audit` + `npm audit` в CI (Часть 11) |
| Secrets in code | `.gitignore` для `keys/`, `.env`; pre-commit `gitleaks` (опц.) |

## 10. Время и журналы

- Контейнеры используют `TZ=Asia/Tashkent`, но логи — в UTC ISO-8601 (`Z`-суффикс)
- Postgres `now()` в UTC, отображение в UI конвертируется на клиенте
- В продакшене — синхронизация хоста через chrony/ntpd на государственный NTP-пул

## 11. Operational checklist (продакшен)

```
[ ] scripts/generate-keys.sh выполнен; keys/ имеют chmod 600
[ ] .env заполнен production-значениями; JWT_SECRET (HS256-fallback) не пустой
[ ] FORCE_HTTPS=true, ENVIRONMENT=production
[ ] CORS_ORIGINS = только https://platform.uz-assets.uz
[ ] TRUSTED_HOSTS = тот же домен + внутренние имена контейнеров
[ ] nginx/certs/* — реальный TLS (Let's Encrypt / государственный УЦ)
[ ] BACKUP_GPG_RECIPIENT настроен; ключ-получатель импортирован в backup-контейнер
[ ] docker compose --profile production up -d
[ ] alembic upgrade head выполнено
[ ] первый user создан скриптом scripts/create_user.py (Часть 2)
[ ] curl https://<host>/healthz вернул 200
[ ] curl -H 'Origin: https://evil' ... — CORS отказывает
[ ] curl -k -I https://<host>/ — присутствуют все security headers
[ ] аудит-лог: первая запись с prev_hash = "000...0"
```

## 12. Что добавляется дальше по дорожной карте

| Часть | ИБ-контроли |
|---|---|
| 2 | `/auth/login` с lockout, `/auth/refresh` ротация refresh-токена, MFA enrol/verify, `require_permission()`, `require_role()`, аудит auth-событий |
| 3 | Скрипт миграции из Firebase с проверкой целостности, dry-run, отчётом |
| 4 | Row-Level Security в Postgres для `organization` (через `current_setting('app.user_id')`) |
| 9 | Workflow-движок одобрения с подписью каждого шага (HMAC + actor) |
| 10 | Treasury 4-eye approval (cfo_dept → cfo_committee), отдельные подписи |
| 11 | CI: pip-audit, npm audit, trivy на образы; SBOM; reproducible builds |
| Deploy | WAF (ModSecurity / Coraza CRS), DDoS на edge, SIEM-интеграция через JSON-логи |

---

## 13. Результаты пентеста (4 мая 2026)

Проведён реальный пентест базового каркаса. Тесты — не симуляция, а исполнение атак против работающего кода.

### Найдено и устранено

| # | Серьёзность | Уязвимость | Исправление |
|---|---|---|---|
| 1 | **CRITICAL** | `python-jose==3.3.0` — CVE-2024-33663 (algorithm confusion), CVE-2024-33664 (JWT bomb). Без активного фикса. | Замена на `PyJWT==2.9.0[crypto]`. python-jose удалён полностью. |
| 2 | **HIGH** | `passlib==1.7.4` не поддерживается с октября 2020. FastAPI рекомендует переход. | Замена на нативный `bcrypt==4.2.0`. passlib удалён. |
| 3 | **CRITICAL** | bcrypt 4.x роняет процесс через `pyo3_runtime.PanicException` при malformed-хэше. Если такой хэш окажется в БД (через миграцию или race) — DoS auth-пути. | `_is_valid_bcrypt_hash()` валидирует формат до `checkpw`, плюс `except BaseException`. |
| 4 | **HIGH** | `SecurityHeadersMiddleware` вызывал `MutableHeaders.pop()` — несуществующий метод. **Все** HTTP-запросы крашились бы на проде. | Замена на `del h["server"]`. |
| 5 | MEDIUM | Password diversity-проверка (`< 4` уникальных символов) пропускала `aaaaaaaaaaaa1A!`. | Усилено: `min_unique = max(6, len // 3)`. |
| 6 | MEDIUM | Common-password blacklist хранил mixed-case строки, `.lower()` не находил совпадений. | Все entries приведены к lowercase. |
| 7 | LOW | Не было защиты от sequence-атак (`1234`, `abcd`, `qwer`). | Добавлена проверка sequences и run-of-3. |

### JWT — отбиты атаки

| Атака | Результат |
|---|---|
| `alg=none` token | ❌ rejected (header.alg ≠ RS256) |
| HS256-confusion с RSA публичным ключом как HMAC-секретом | ❌ rejected (алгоритм не совпадает) |
| Tampered payload | ❌ rejected (InvalidSignatureError) |
| Expired token | ❌ rejected (ExpiredSignatureError) |
| Wrong issuer / audience | ❌ rejected |
| Type confusion (refresh→access) | ❌ rejected |
| Oversized token (>8 KB) | ❌ rejected до парсинга |
| JWE 5-сегментный токен (CVE-2024-33664 shape) | ❌ rejected (только JWS принимается) |
| Forged kid | ❌ rejected (Unknown key id) |

### HTTP-уровень — отбиты атаки

| Атака | Результат |
|---|---|
| Untrusted Host header (`evil.attacker.com`) | ❌ 400 (TrustedHost) |
| CRLF в Host | ❌ 400 |
| Bad CORS Origin (`evil.attacker.com`) | ✅ ACAO не отражён |
| Body 50 MB через spoofed Content-Length | ❌ 413 |
| Method tunneling (`X-HTTP-Method-Override: DELETE`) | ❌ игнорируется |
| TRACE / CONNECT / DELETE на read endpoints | ❌ 405 |
| Path traversal: `/../etc/passwd`, `/.env`, `/.git/config`, URL-encoded `%2e%2e`, null-byte `%00` | ❌ 404 |
| Reflected XSS в URL-параметрах | ❌ JSON-ответ не отражает HTML |

### SAST — статический анализ

| Категория | Результат |
|---|---|
| SQL injection (поиск `text(f"...")`, `.format()`, `%s`, исполнение строки) | **0 найдено** — все ORM-запросы через `select()` builder и параметризованный `text()` |
| Path traversal (open + user input) | **0 найдено** |
| Dangerous constructs (`eval`, `exec`, `pickle.loads`, `yaml.load`) | **0 найдено** |
| Weak crypto (MD5, SHA1, DES, 3DES, RC4) | **0 найдено** в коде приложения |
| Hardcoded `DEBUG=True` или `debug=True` | **0 найдено** |
| Bandit (severity ≥ medium) | **0 issues** |

### Crypto — целостность

| Контроль | Результат |
|---|---|
| Fernet round-trip | ✅ |
| Tampered ciphertext detection | ✅ ValueError при изменении любого байта |
| IV-randomization (одинаковый plaintext → разные ciphertext) | ✅ |
| Unicode + 1 MB payloads | ✅ |
| Audit HMAC-chain: forge без секрета | ❌ невозможно (HMAC-SHA256, нужен audit_hmac.key) |
| Audit chain: удаление записи | ❌ ломается видимо (`prev_hash` не совпадает) |
| Audit chain: подмена payload | ❌ ломается (entry_hash меняется) |

### Password policy — отбиты слабые

`aaaaaaaaaaaa1A!`, `Uzbekistan2026!`, `Tashkent2026!`, `Password1234!`, `AbcdEfghIjkl1!`, `Qwerty12345!@`, `aaa1Bb#cccDef` — все отклонены с правильными кодами (`low_diversity` / `common_password` / `sequence` / `repeats`).

### Что **остаётся защитить инфраструктурно** (вне приложения)

- **DDoS volumetric** — нужен edge-уровень (Cloudflare / Yandex Cloud Edge / uzcloud) перед nginx. Базовый rate-limit на nginx справляется с обычным spam'ом, но не с distributed flooding.
- **TLS pin** — для критичных клиентов (мобильные приложения) — certificate pinning к нашему фиксированному сертификату.
- **Network segmentation** — backend и postgres в одной internal-сети, но в проде — отдельный VPC, security groups, postgres только из IP backend'а.
- **Bastion / jump-host** — административный доступ к продакшену только через bastion с MFA.
- **WAF на edge** — ModSecurity / Coraza CRS (Часть 11) — отлавливает OWASP Top-10 паттерны до того как они попадут в код.

---

## 14. Подсистема СЕКРЕТНЫХ ДОКУМЕНТОВ

> **Текущий каркас покрывает базовый госуровень, но недостаточен для хранения документов с грифом „СЕКРЕТНО" / „СОВЕРШЕННО СЕКРЕТНО" по ЗРУ-543.**

Что должно быть добавлено отдельной подсистемой (после Части 11):

### 14.1 Шифрование документов

- **Envelope encryption**: каждый документ шифруется уникальным DEK (Data Encryption Key); DEK шифруется KEK (Key Encryption Key) из HSM/KMS. Формат: `{dek_encrypted, iv, ciphertext, hmac}`.
- **HSM/KMS обязательно** в проде — софтверный Fernet недостаточен. Варианты для UZ: государственный KMS (если будет), Hashicorp Vault Enterprise с HSM-бэкендом, или CloudHSM при наличии.
- **Криптографическое уничтожение** (cryptographic shredding) — удаление документа = удаление его DEK. Резервные копии становятся непригодны через минуты.
- **Per-classification keys** — отдельный KEK на каждый уровень секретности (CONFIDENTIAL / SECRET / TOP SECRET). Компрометация одного не раскрывает остальные.

### 14.2 Контроль доступа

- **Классификационные уровни**: UNCLASSIFIED / CONFIDENTIAL / SECRET / TOP SECRET — отдельная таблица `documents.classification`.
- **Need-to-know**: даже при наличии clearance — обязательная ACL-запись. Таблица `document_acl(document_id, user_id, granted_by, granted_at, expires_at, reason)`.
- **MAC (Mandatory Access Control)**: пользователь не может прочитать документ выше своего clearance level, даже если в ACL есть запись.
- **Bell-LaPadula no-read-up / no-write-down**: реализуется на уровне сервиса.
- **Hardware MFA обязательно** для уровней SECRET+: FIDO2/WebAuthn ключи (YubiKey 5 FIPS), не TOTP. TOTP допустим только для UNCLASSIFIED/CONFIDENTIAL.

### 14.3 Аудит чтения

- **Каждое чтение секретного документа = запись в audit_log** с полями: `user_id, document_id, classification, ip, user_agent, session_id, read_duration_seconds, page_numbers, timestamp`.
- **Anomaly detection**: пользователь, который обычно читает 5 документов в день, вдруг читает 500 — алерт.
- **Bulk export запрещён** для SECRET+. Только постраничный просмотр.

### 14.4 Watermarking

- Каждая страница каждого документа SECRET+ выводится с **видимым водяным знаком**: ФИО + email + IP + timestamp + session_id + первые 8 символов хэша HMAC(secret, user_id|document_id|session_id).
- Если документ утечёт — по водяному знаку идентифицируется источник.

### 14.5 Multi-eyes принцип

- **Декласcификация**, **массовый экспорт**, **удаление**, **выдача внешнего доступа** требуют 2+ независимых утверждений (например, `cfo_committee` + `audit_viewer`-confirm).
- Каждое утверждение — отдельная подпись с привязкой к JWT-сессии и IP.

### 14.6 Air-gap deployment

- Опция: deploy без интернет-egress. Только UPDATE через подписанные офлайн-пакеты от Anthropic.
- AI-модуль либо отключён, либо использует локальную on-prem inference (Llama / Mistral self-hosted).
- Backup — на физический носитель, изъятый из системы.

### 14.7 Tamper-evident storage

- Merkle tree всех документов: каждый документ → `H(doc_content)` → лист дерева → корень публикуется в audit_log при каждом изменении.
- Любое изменение документа отражается в новом корне; история корней сравнима — можно доказать, что документ не менялся.

### 14.8 Compliance (Узбекистан)

- **ЗРУ-543** «О защите государственных секретов» — основной закон.
- **Постановление Президента ПП-3724** «О мерах по дальнейшему совершенствованию системы обеспечения информационной безопасности».
- **O‘zDSt 1092:2009** — терминология ИБ.
- **Сертификация ИС** в Государственном центре кибербезопасности (Davlat kibernetik xavfsizlik markazi) при Госспецсвязи — для систем, обрабатывающих гостайну.
- Допуск персонала к гостайне (форма 2/3) — **процедурный** контроль вне платформы, но платформа должна вести реестр допусков.

### 14.9 Что нужно сделать ДО загрузки секретных документов

```
[ ] Часть 11 завершена (CI/CD с pip-audit + trivy + SBOM)
[ ] HSM/KMS интегрирован — DEK не хранятся в файловой системе
[ ] Hardware MFA обязателен для всех ролей с доступом к SECRET+
[ ] Watermarking реализован для PDF-рендеринга
[ ] Anomaly detection на read-частоту
[ ] Multi-eyes implemented для declassify/export/delete
[ ] Аудит цепочки покрыт ВСЕ document.read события
[ ] Air-gap deployment протестирован отдельно
[ ] Сертификация ИС в Госкомцентре кибербезопасности получена
[ ] Personnel reaching SECRET+ имеют форму допуска 2/3
[ ] Penetration test от внешней команды (рекомендую — раз в 6 месяцев)
[ ] Disaster recovery: PITR + offline cold backup на физический носитель
```

**Пока эти пункты не реализованы — платформа НЕ должна использоваться для документов с грифом „СЕКРЕТНО" и выше.** Текущий каркас (Часть 1 + ИБ-baseline) подходит для UNCLASSIFIED и ограниченно — для CONFIDENTIAL.
