# S3 Object Storage — подключение для администратора

## Как работает storage в платформе

Файлы (вложения к задачам/проектам/компаниям) хранятся через **storage abstraction layer**. Два бэкенда из коробки:

| Бэкенд | Когда использовать | Что делает |
|---|---|---|
| `local` (default) | dev / single-host prod | Кладёт файлы в Docker volume `backend_uploads:/app/uploads`. Signed-URL'ы выдаёт через внутренний endpoint `/api/attachments/raw/{key}?exp=...&sig=...` (HMAC-подпись + 5-минутный TTL) |
| `s3` | prod, distributed | S3-совместимое объектное хранилище (AWS S3, MinIO, **uzcloud Object Storage**). Signed-URL'ы — нативные S3 presigned URLs |

Переключение через **одну переменную окружения** `STORAGE_BACKEND`. Никаких изменений в коде приложения — slug-уровень API остаётся одинаковым.

---

## Переключение на S3 (4 шага)

### Шаг 1. Создать bucket в uzcloud Object Storage

1. Зайти на https://console.uzcloud.uz/ → Object Storage
2. **Create bucket**:
   - Name: `uzassets-platform-prod` (или другой)
   - Region: `tashkent-1`
   - **Public access: BLOCKED** ⚠️ — все скачивания через signed URLs
   - **Versioning: enabled** — позволяет откатывать случайно перезаписанные файлы
   - **Server-side encryption: AES256** — at-rest шифрование

3. Создать **IAM user** (или access key) с минимальными правами:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "AppRW",
         "Effect": "Allow",
         "Action": [
           "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
           "s3:HeadObject", "s3:ListBucket"
         ],
         "Resource": [
           "arn:aws:s3:::uzassets-platform-prod",
           "arn:aws:s3:::uzassets-platform-prod/*"
         ]
       }
     ]
   }
   ```
   - Сохрани `Access key ID` и `Secret access key` — они будут в `.env`

### Шаг 2. Заполнить env-переменные

В `backend/.env.uzassets006` (или активный env-file) добавить:

```bash
# ─── File storage ────────────────────────────────────────────
STORAGE_BACKEND=s3

# uzcloud Object Storage
STORAGE_S3_ENDPOINT_URL=https://s3.uzcloud.uz
STORAGE_S3_BUCKET=uzassets-platform-prod
STORAGE_S3_REGION=tashkent-1
STORAGE_S3_ACCESS_KEY=AKIAxxxxxxxxxxxxxxxx
STORAGE_S3_SECRET_KEY=*****************************
STORAGE_S3_FORCE_PATH_STYLE=true        # обязательно для uzcloud / MinIO
STORAGE_S3_SSE=AES256                   # server-side encryption
```

Для **AWS S3** (если когда-нибудь переключитесь):
```bash
STORAGE_S3_ENDPOINT_URL=                # пусто — boto использует AWS default
STORAGE_S3_BUCKET=uzassets-platform-prod
STORAGE_S3_REGION=eu-central-1
STORAGE_S3_FORCE_PATH_STYLE=false
```

### Шаг 3. Recreate backend

```bash
docker compose --project-directory . \
  --env-file backend/.env.uzassets006 \
  -f backend/docker-compose.yml \
  up -d --force-recreate backend
```

### Шаг 4. Verify

```bash
docker exec uza-backend env | grep STORAGE_
# Должно вывести: STORAGE_BACKEND=s3 + S3_* переменные

# Smoke-test: загрузить файл через API и проверить что он попал в bucket
curl -sk -X POST https://uz-assets040/api/attachments/task/<TASK_ID> \
  -H "Authorization: Bearer <JWT>" \
  -F "file=@/path/to/test.pdf"
# Ожидается: 201 + JSON с id, filename, download_url

# Список объектов в bucket (через aws CLI с теми же credentials)
aws --endpoint-url=https://s3.uzcloud.uz s3 ls s3://uzassets-platform-prod/tasks/
```

---

## Структура ключей в bucket

```
tasks/{company_id}/{year}/{task_id}/{uuid}-{filename}
projects/{company_id}/{year}/{project_id}/{uuid}-{filename}
company/{company_id}/{year}/{category}/{uuid}-{filename}
```

Преимущества префиксов:
- **Per-company access scoping** — IAM policy может выдавать пользователю доступ только к `arn:aws:s3:::bucket/tasks/{their_company_id}/*`
- **Lifecycle rules** — можно настроить автоудаление старых сезонных данных по году
- **Cost allocation** — биллинг можно разбить по company prefix

---

## Безопасность

| Слой | Что защищает |
|---|---|
| **Bucket policy** | Public access blocked — никто не может скачать без presigned URL |
| **Server-side encryption** | `STORAGE_S3_SSE=AES256` — файлы шифруются на стороне S3 at-rest |
| **HTTPS** | uzcloud endpoint обязан быть `https://` — без TLS S3 не работает |
| **Signed URLs** | TTL = 300 секунд (5 минут). После истечения URL перестаёт работать — нельзя поделиться долгоживущей ссылкой |
| **Per-company scope** | Backend `ensure_company_access()` проверяет что юзер имеет доступ к компании файла ДО выдачи signed URL |
| **MIME whitelist** | Только: pdf, doc(x), xls(x), ppt(x), png, jpg/jpeg, webp, zip, txt, csv |
| **Max size** | 25 MB (nginx + middleware lock) |
| **Permission gate** | Upload требует `tasks.edit` (task/project) или `companies.edit` (company-level files) |

---

## Резервное копирование

S3 / uzcloud Object Storage **не покрывается** существующим `pg_dump` backup container'ом — он бэкапит только Postgres. Для файлов нужен отдельный канал.

### Вариант А: Cross-region replication (uzcloud)

В консоли bucket → **Replication** → создать правило:
- Source: `uzassets-platform-prod` (tashkent-1)
- Destination: `uzassets-platform-backup` (другой регион / резервный bucket)
- Schedule: continuous (каждое изменение реплицируется автоматически)

### Вариант Б: Периодический sync через rclone (cron)

```bash
# В backup-контейнере добавить:
rclone sync s3:uzassets-platform-prod \
            backup-s3:uzassets-platform-backup \
            --transfers 8 --checkers 16 --fast-list
```

Расписание — каждые 6 часов (как pg_dump).

---

## Миграция существующих файлов (если уже есть на local)

Если переходишь со `local` на `s3` и в `backend_uploads` уже есть файлы — нужна миграция:

```bash
# 1. Установить awscli внутри backend container
docker exec uza-backend pip install awscli

# 2. Залить весь uploads volume в S3
docker exec uza-backend aws --endpoint-url=$STORAGE_S3_ENDPOINT_URL \
  s3 cp /app/uploads s3://$STORAGE_S3_BUCKET/ --recursive --sse AES256

# 3. Проверить что объекты появились
docker exec uza-backend aws --endpoint-url=$STORAGE_S3_ENDPOINT_URL \
  s3 ls s3://$STORAGE_S3_BUCKET/ --recursive | wc -l

# 4. Сменить STORAGE_BACKEND=s3 + recreate backend (шаги 2-3 выше)

# 5. Опционально — удалить local-файлы после verify
docker exec uza-backend rm -rf /app/uploads/*
```

Storage keys (`task_attachments.storage_key`, `company_attachments.storage_key`) — **одинаковые** на local и S3, миграция не требует DB-обновлений.

---

## Откат на local

Если что-то пошло не так:
```bash
# В .env удалить или закомментировать:
# STORAGE_BACKEND=s3

# Recreate
docker compose ... up -d --force-recreate backend
```

Backend перейдёт на `local` (дефолт). Файлы, залитые в S3, перестанут отдаваться — нужно либо вернуть `s3` обратно, либо `aws s3 cp` файлы обратно в `/app/uploads`.

---

## Мониторинг

| Метрика | Где смотреть |
|---|---|
| Объём bucket | uzcloud console → Object Storage → bucket → Metrics |
| Запросы S3 (4xx / 5xx) | uzcloud console → bucket → Access logs (если включены) |
| Backend ошибки на upload/download | `docker logs uza-backend \| grep storage` |
| Prometheus | `/metrics` endpoint — добавится metric `uza_storage_uploads_total{outcome="success|fail"}` (TODO) |

---

## Troubleshooting

| Симптом | Причина | Что делать |
|---|---|---|
| `403 SignatureDoesNotMatch` | Wrong access key/secret | Проверь `STORAGE_S3_ACCESS_KEY`/`SECRET_KEY` |
| `NoSuchBucket` | Bucket name typo | Проверь `STORAGE_S3_BUCKET` |
| `RequestTimeTooSkewed` | Часы backend контейнера разъехались | `docker exec uza-backend date` — должен совпадать с реальным временем ±15 мин. Включить NTP в host |
| Загрузка работает, скачивание 403 | Public access не заблокирован, но signed URL испорчен | Проверь время backend (presigned URL содержит timestamp); проверь `STORAGE_S3_ENDPOINT_URL` без trailing slash |
| `aiobotocore.session not found` | Module не установлен в running контейнере | `docker exec uza-backend pip install aiobotocore==2.15.2` или rebuild backend image |
