#!/usr/bin/env bash
# pg_dump → gzip → optional GPG → SHA256 manifest.
# Designed to be invoked from cron inside the uza-backup container.
set -euo pipefail

: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_GPG_RECIPIENT:=}"
: "${BACKUP_REQUIRE_ENCRYPTION:=true}"

# Hardening: refuse to write unencrypted backups unless explicitly opted out.
# The DB dump contains all bcrypt hashes, MFA secrets (Fernet-encrypted in the
# row, but the row + encryption key file are on the same host), audit chain,
# webhook secrets — a backup on disk is effectively as sensitive as the DB.
if [ "${BACKUP_REQUIRE_ENCRYPTION}" = "true" ] && [ -z "${BACKUP_GPG_RECIPIENT}" ]; then
    echo "[$(date -u -Iseconds)] backup ABORT: BACKUP_REQUIRE_ENCRYPTION=true but BACKUP_GPG_RECIPIENT is empty." >&2
    echo "  Set BACKUP_GPG_RECIPIENT=<email> with the public key in gpg keyring," >&2
    echo "  or set BACKUP_REQUIRE_ENCRYPTION=false to explicitly accept plaintext backups." >&2
    exit 2
fi

# Verify the GPG key is actually importable BEFORE we spend minutes dumping.
if [ -n "${BACKUP_GPG_RECIPIENT}" ]; then
    if ! gpg --batch --list-keys "${BACKUP_GPG_RECIPIENT}" > /dev/null 2>&1; then
        echo "[$(date -u -Iseconds)] backup ABORT: GPG recipient '${BACKUP_GPG_RECIPIENT}' not in keyring." >&2
        exit 3
    fi
fi

TS=$(date -u +%Y%m%dT%H%M%SZ)
BASE_NAME="${POSTGRES_DB}_${TS}"
TMP_DIR=$(mktemp -d)
ARCHIVE="${BACKUP_DIR}/${BASE_NAME}.sql.gz"

export PGPASSWORD="${POSTGRES_PASSWORD}"

echo "[$(date -u -Iseconds)] backup START → ${ARCHIVE}"

# Stream dump → gzip directly to disk (never lands uncompressed).
pg_dump \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT}" \
    --username="${POSTGRES_USER}" \
    --no-owner --no-acl --verbose \
    "${POSTGRES_DB}" 2>"${TMP_DIR}/dump.log" \
  | gzip -9 > "${ARCHIVE}"

DUMP_BYTES=$(stat -c %s "${ARCHIVE}" 2>/dev/null || wc -c < "${ARCHIVE}")
if [ "${DUMP_BYTES}" -lt 1024 ]; then
    echo "[$(date -u -Iseconds)] backup FAILED: archive too small (${DUMP_BYTES} bytes)"
    cat "${TMP_DIR}/dump.log" >&2
    rm -f "${ARCHIVE}"
    exit 1
fi

# Optional GPG encryption (BACKUP_GPG_RECIPIENT must be in the keyring).
if [ -n "${BACKUP_GPG_RECIPIENT}" ]; then
    echo "[$(date -u -Iseconds)] backup ENCRYPT → ${BACKUP_GPG_RECIPIENT}"
    gpg --batch --yes --trust-model always \
        --recipient "${BACKUP_GPG_RECIPIENT}" \
        --output "${ARCHIVE}.gpg" \
        --encrypt "${ARCHIVE}"
    rm -f "${ARCHIVE}"
    ARCHIVE="${ARCHIVE}.gpg"
fi

# SHA-256 manifest.
SUM=$(sha256sum "${ARCHIVE}" | awk '{print $1}')
echo "${SUM}  $(basename "${ARCHIVE}")" >> "${BACKUP_DIR}/SHA256SUMS"

echo "[$(date -u -Iseconds)] backup OK ($(du -h "${ARCHIVE}" | cut -f1), sha=${SUM:0:16}…)"
rm -rf "${TMP_DIR}"

# Prune old archives.
"$(dirname "$0")/prune.sh"
