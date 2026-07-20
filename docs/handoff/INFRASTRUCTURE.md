# Инфраструктура

## Схема развёртывания

![Инфраструктура](diagrams/infrastructure.png)

Одна виртуальная машина, весь стек в Docker Compose (сеть `uza-net`). Наружу
опубликован только nginx (80/443). Backend, PostgreSQL, бот и backup-воркер — во
внутренней сети без публикации портов на хост.

## Контейнеры и образы

| Контейнер | Образ | Публикация | Лимиты (compose) |
|---|---|---|---|
| `uza-nginx` | nginx 1.27-alpine (+ собранная статика) | 80, 443 | 0.5 vCPU |
| `uza-backend` | Python 3.12-slim (FastAPI) | expose 8000 (внутр.) | 2 vCPU / 2 GB |
| `uza-postgres` | postgres:16-alpine | expose 5432 (внутр.) | 1.5 vCPU / 1 GB |
| `uza-tg-bot` | Python (aiogram) | — | 0.5 vCPU / 256 MB |
| `uza-backup` | alpine + postgresql-client + gnupg | — | — |

Backend монтирует код read-only (`:ro`) — процесс в контейнере не может переписать
`/app` (защита от инъекции кода); запись только в тома `uploads` и `certs`.
Контейнеры запускаются с `no-new-privileges` и `cap_drop: ALL` (nginx добавляет
только `NET_BIND_SERVICE` для портов <1024).

## Параметры сервера (текущий прод)

| Параметр | Значение |
|---|---|
| ОС | Ubuntu 24.04 LTS |
| CPU | 2 vCPU |
| RAM | ~4 GB |
| Диск | ~40 GB SSD |
| Размещение БД/приложения | внутренняя сеть, наружу — только nginx (443) |

Требования к слою (ориентировочно, для среды): сервер СУБД — 2 vCPU / 4 GB, SSD с
резервированием; сервер приложений — 2 vCPU / 2 GB; обратный прокси — 0.5 vCPU;
электропитание с UPS; исходящий доступ к внешним ИС и GitHub (для автодеплоя).

## Текущая нагрузка

Снимок (типичное состояние):

| Метрика | Значение |
|---|---|
| Load average (1/5/15 мин) | ~0.10 (при 2 vCPU — запас значительный) |
| RAM использовано | ~1.6 GB из ~4 GB (доступно ~2.3 GB) |
| Диск | ~66% занято |
| CPU по контейнерам | backend ~0.2%, postgres ~0.1%, bot ~0.2%, nginx ~0% (в покое) |
| RAM по контейнерам | backend ~340 MB, postgres ~250 MB, bot ~160 MB, nginx ~9 MB |

Как снять актуальные метрики — см. RUNBOOK.md → «Наблюдаемость».

## Планирование мощностей

Проектные показатели: 22 предприятия (с расширением), ≥500 зарегистрированных
пользователей, ≥100 одновременно работающих, время отклика ≤10 с, доступность ≥97%.

Текущая утилизация (load ~0.1 при 2 vCPU, RAM ~40%) показывает большой запас на
типовой нагрузке. Рекомендации по росту:

- **Вертикально:** при устойчивом росте одновременных пользователей — 4 vCPU / 8 GB;
  поднять `cpus`/`memory` лимиты backend и postgres в `docker-compose.yml`.
- **Диск:** держать <75%; основной рост — `postgres_data` и `backups`. При
  приближении к лимиту увеличить том/диск, проверить retention бэкапов (30 дней).
- **Backend-воркеры:** для прод переопределить команду на несколько Uvicorn-воркеров
  (`COMPOSE_BACKEND_CMD='uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
  --proxy-headers --forwarded-allow-ips=172.16.0.0/12'`), убрав `--reload`.
- **БД:** при росте объёма — тюнинг PostgreSQL (`shared_buffers`, `work_mem`,
  пул соединений), контроль медленных запросов; вынести БД на отдельный узел.
- **Масштаб:** при необходимости — реплика PostgreSQL для чтения и несколько
  реплик backend за nginx (stateless-приложение это допускает).

Ключевые точки контроля: доля 5xx, время отклика p95, глубина очереди уведомлений
(outbox), лаг/ошибки интеграционных обменов, свободное место на диске.

## Автодеплой

`master` разворачивается автоматически: VM тянет `origin/master` по systemd-таймеру
(`ops/vm-autodeploy/`, установка один раз через `install.sh`). Скрипт `deploy.sh`
идемпотентен: при новом коммите делает `git reset --hard origin/master`, пересобирает
образ nginx (в него запечён фронт) и перезапускает backend (backend монтирует код,
runtime-миграции применяются при старте). Ключ `jwt_public.pem` сохраняется поверх
reset (окруженческий).

Порядок: `git push origin master` → в течение ~2 минут изменения на проде.

## Резервное копирование

Backup-воркер по расписанию (по умолчанию каждые 6 часов) делает `pg_dump` → gzip →
шифрование GPG → SHA-256-манифест, складывает в том `backups`, retention 30 дней.
Без указанного получателя GPG (`BACKUP_GPG_RECIPIENT`) воркер намеренно отказывается
писать незашифрованный архив. Восстановление — см. RUNBOOK.md.

## Клон базы данных

Снять полный дамп БД (схема + данные) из контейнера PostgreSQL:

```bash
# логический дамп (custom-формат, сжатый) — рекомендуется
docker exec -t uza-postgres pg_dump -U uza -d uzassets -Fc -f /tmp/uzassets.dump
docker cp uza-postgres:/tmp/uzassets.dump ./uzassets.dump

# или plain SQL
docker exec -t uza-postgres pg_dump -U uza -d uzassets > uzassets.sql

# только схема (без данных)
docker exec -t uza-postgres pg_dump -U uza -d uzassets --schema-only > schema.sql
```

Восстановить в чистую БД:

```bash
# из custom-дампа
docker cp ./uzassets.dump uza-postgres:/tmp/uzassets.dump
docker exec -t uza-postgres pg_restore -U uza -d uzassets --clean --if-exists /tmp/uzassets.dump

# из plain SQL (через stdin, чтобы не терять кириллицу)
cat uzassets.sql | docker exec -i uza-postgres psql -U uza -d uzassets
```

Примечание: при переносе на другую среду пароль владельца БД и окруженческие ключи
(`jwt_public.pem` и др.) задаются заново под целевое окружение.
