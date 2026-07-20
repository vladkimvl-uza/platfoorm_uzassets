# Runbook (эксплуатация)

Все команды выполняются на VM. Docker Compose вызывается из корня проекта; для
production-профиля указывается файл и профиль:

```bash
dc() { docker compose --project-directory . -f backend/docker-compose.yml --profile production "$@"; }
```

## Развёртывание

Штатно — через автодеплой: `git push origin master` → VM подхватывает по таймеру
(~2 минуты). Ручной деплой на VM:

```bash
cd /home/ubuntu/<repo>
bash ops/vm-autodeploy/deploy.sh      # git reset origin/master + build nginx + restart backend
```

Проверка:

```bash
dc ps
curl -skI https://<host>/            # SPA отдаётся
curl -sk  https://<host>/api/health  # backend жив
git rev-parse --short HEAD           # задеплоенный коммит
```

Frontend запечён в образ nginx: после изменений фронта нужно `dc build nginx` и
`dc up -d --force-recreate nginx`. Backend монтирует код — достаточно `dc restart
backend` (runtime-миграции применяются при старте).

## Ключи и секреты

В `backend/.env` (не в git). Минимум:

- `POSTGRES_PASSWORD` — пароль БД;
- `JWT` — пара RS256: `backend/keys/jwt_private.pem` + `jwt_public.pem`;
- `FERNET_KEY_PATH` (`keys/fernet.key`) — шифрование полей;
- `AUDIT_HMAC_SECRET_PATH` (`keys/audit_hmac.key`) — целостность аудита;
- `AI_API_KEY`, `LLM_API_URL`, `AI_MODEL_*` — движок ИИ (опционально);
- `TELEGRAM_BOT_TOKEN`, `BOT_CALLBACK_SECRET` — Telegram (опционально);
- `BACKUP_GPG_RECIPIENT` — получатель GPG для шифрования бэкапов.

Генерация ключей (пример):

```bash
# JWT RS256
openssl genrsa -out backend/keys/jwt_private.pem 2048
openssl rsa -in backend/keys/jwt_private.pem -pubout -out backend/keys/jwt_public.pem
# Fernet и HMAC — случайные ключи
python -c "from cryptography.fernet import Fernet; open('backend/keys/fernet.key','wb').write(Fernet.generate_key())"
head -c 32 /dev/urandom | base64 > backend/keys/audit_hmac.key
```

`jwt_public.pem` — окруженческий: при переносе не затирать чужим (иначе проверка
подписи токенов падает и всех выбрасывает на логин).

## Резервное копирование и восстановление

Копии создаёт `uza-backup` (каждые 6 ч, GPG-шифрование, retention 30 дней) в том
`backups`. Список и ручной прогон:

```bash
docker exec uza-backup ls -lh /backups
docker exec uza-backup /usr/local/bin/backup.sh   # ручной бэкап
```

Восстановление БД — см. INFRASTRUCTURE.md → «Клон базы данных» (`pg_restore` /
`psql`). Перед восстановлением остановить backend, после — запустить и проверить.

## Наблюдаемость

```bash
dc ps                                   # статусы + health
dc logs -f backend                      # логи backend (JSON)
dc logs --since 30m bot                 # логи бота
docker stats --no-stream                # CPU/RAM по контейнерам
df -h /                                 # диск
free -h ; uptime                        # RAM и load average
docker inspect -f '{{.State.Health.Status}}' uza-backend
```

Метрики Prometheus и события Sentry — если настроены соответствующие переменные.

## Типовые операции

Просмотр таблицы / данных:

```bash
docker exec -it uza-postgres psql -U uza -d uzassets -c "\dt"      # список таблиц
docker exec -it uza-postgres psql -U uza -d uzassets              # интерактив
```

Перезапуск компонента:

```bash
dc restart backend        # backend
dc up -d --force-recreate nginx   # nginx (после пересборки фронта)
dc restart bot            # бот
```

## Инциденты

| Симптом | Проверка / действие |
|---|---|
| Сайт не открывается | `dc ps` (nginx up?), `dc logs nginx`; TLS-сертификат не истёк? |
| API 5xx | `dc logs backend`; БД жива (`dc ps` postgres healthy)? миграции применились? |
| «Выброс на логин после входа» | не затёрт ли `jwt_public.pem` при деплое (окруженческий ключ) |
| Не приходят уведомления Telegram | `dc logs bot`; глубина `telegram_outbox`; `TELEGRAM_BOT_TOKEN` задан? |
| Автодеплой не срабатывает | статус таймера `systemctl status uza-autodeploy.timer`; доступ VM к GitHub |
| Диск заполняется | `df -h`; размер `postgres_data`/`backups`; retention бэкапов |
| Не работает голосовой ввод / камера | серверный заголовок `Permissions-Policy` в nginx (должен разрешать нужную фичу) |

## Гейты качества (перед деплоем)

```bash
# backend
python -m py_compile <изменённые модули>
pytest                       # тесты на testcontainers
# frontend
cd frontend && npx vite build   # эталонная прод-сборка (exit 0)
```
