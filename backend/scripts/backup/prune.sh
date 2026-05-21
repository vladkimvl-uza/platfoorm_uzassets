#!/usr/bin/env bash
# Delete backup archives older than BACKUP_RETENTION_DAYS.
set -euo pipefail
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_RETENTION_DAYS:=30}"

REMOVED=$(find "${BACKUP_DIR}" -maxdepth 1 -type f \( -name "*.sql.gz" -o -name "*.sql.gz.gpg" \) \
    -mtime +"${BACKUP_RETENTION_DAYS}" -print -delete | wc -l)
echo "[$(date -u -Iseconds)] prune: removed ${REMOVED} archives older than ${BACKUP_RETENTION_DAYS}d"
