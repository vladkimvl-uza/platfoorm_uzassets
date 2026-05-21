#!/usr/bin/env bash
# Apply least-privilege DB role setup. Idempotent — re-run for password rotation.
#
# Usage:
#   APP_DB_PASSWORD=...
#   BACKUP_DB_PASSWORD=...
#   POSTGRES_PASSWORD=...   (superuser, for connecting to apply grants)
#   POSTGRES_USER=uza
#   POSTGRES_DB=uzassets
#   ./setup-db-users.sh
#
# From host (compose project root):
#   docker compose exec -e APP_DB_PASSWORD=$APP_DB_PASSWORD \
#                         -e BACKUP_DB_PASSWORD=$BACKUP_DB_PASSWORD \
#                         postgres bash /backup-scripts/setup-db-users.sh
#
# Or run via psql directly with the SQL file (preferred — no shell layer):
#   docker compose exec postgres psql -U uza -d uzassets \
#       -v app_password="'$APP_DB_PASSWORD'" \
#       -v backup_password="'$BACKUP_DB_PASSWORD'" \
#       -v app_db="uzassets" \
#       -f /scripts/setup-db-users.sql

set -euo pipefail

: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required (>=20 chars random)}"
: "${BACKUP_DB_PASSWORD:?BACKUP_DB_PASSWORD is required (>=20 chars random)}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required (superuser)}"
: "${POSTGRES_USER:=uza}"
: "${POSTGRES_DB:=uzassets}"
: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"

# Minimal password length check — defense against weak rotation.
if [ ${#APP_DB_PASSWORD} -lt 20 ]; then
    echo "ABORT: APP_DB_PASSWORD must be at least 20 chars" >&2; exit 2
fi
if [ ${#BACKUP_DB_PASSWORD} -lt 20 ]; then
    echo "ABORT: BACKUP_DB_PASSWORD must be at least 20 chars" >&2; exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SQL_FILE="${SCRIPT_DIR}/setup-db-users.sql"

if [ ! -f "${SQL_FILE}" ]; then
    echo "ABORT: SQL file not found at ${SQL_FILE}" >&2; exit 3
fi

export PGPASSWORD="${POSTGRES_PASSWORD}"

# Single-quote escape so the password is treated as a literal in psql var.
esc() { printf "%s" "$1" | sed "s/'/''/g"; }

psql -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" \
     -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
     -v ON_ERROR_STOP=1 \
     -v app_password="'$(esc "${APP_DB_PASSWORD}")'" \
     -v backup_password="'$(esc "${BACKUP_DB_PASSWORD}")'" \
     -v app_db="${POSTGRES_DB}" \
     -f "${SQL_FILE}"
