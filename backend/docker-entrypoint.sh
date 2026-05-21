#!/bin/sh
# UzAssets backend entrypoint.
#
# Runs alembic migrations against the admin URL (superuser, can DDL),
# then starts uvicorn.
#
# Behaviour controlled by env:
#   RUN_MIGRATIONS=1   (default) — apply pending migrations on startup
#   RUN_MIGRATIONS=0             — skip (useful for ephemeral debug runs)
#
# DATABASE_URL_ADMIN must be set (compose / uzcloud env). Falls back to
# DATABASE_URL_SYNC if admin URL is missing — but alembic may then fail
# on DDL if the runtime user lacks permission. Set it explicitly in prod.
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] Waiting for database to be reachable..."
    # Simple TCP probe loop — gives postgres up to 60s to come up.
    DB_HOST="$(echo "${DATABASE_URL_ADMIN:-${DATABASE_URL_SYNC:-${DATABASE_URL}}}" | sed -E 's|.*@([^:/]+).*|\1|')"
    DB_PORT="$(echo "${DATABASE_URL_ADMIN:-${DATABASE_URL_SYNC:-${DATABASE_URL}}}" | sed -E 's|.*@[^:]+:([0-9]+).*|\1|')"
    DB_PORT="${DB_PORT:-5432}"
    i=0
    while ! python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('${DB_HOST}', ${DB_PORT}))" 2>/dev/null; do
        i=$((i+1))
        if [ $i -ge 30 ]; then
            echo "[entrypoint] Database not reachable at ${DB_HOST}:${DB_PORT} after 60s — giving up."
            exit 1
        fi
        sleep 2
    done

    echo "[entrypoint] Running alembic upgrade head..."
    alembic upgrade head
    echo "[entrypoint] Migrations applied."
else
    echo "[entrypoint] RUN_MIGRATIONS=0 — skipping migrations."
fi

echo "[entrypoint] Starting uvicorn..."
exec "$@"
