#!/usr/bin/env bash
# Daily SSL certificate expiry check. Designed to run inside the backup
# container (or any container with openssl + the nginx cert volume mounted
# read-only). Alerts when cert expires within ${SSL_EXPIRY_WARN_DAYS}.
#
# Exit code:
#   0 — all certs healthy
#   1 — at least one cert expires soon
#   2 — at least one cert is invalid / missing
set -euo pipefail

: "${SSL_CERT_PATH:=/etc/nginx/certs/fullchain.pem}"
: "${SSL_EXPIRY_WARN_DAYS:=30}"

if [ ! -f "${SSL_CERT_PATH}" ]; then
    echo "[$(date -u -Iseconds)] ssl-check ABORT: cert file not found at ${SSL_CERT_PATH}" >&2
    exit 2
fi

EXPIRY_DATE=$(openssl x509 -enddate -noout -in "${SSL_CERT_PATH}" | sed 's/^notAfter=//')
EXPIRY_TS=$(date -d "${EXPIRY_DATE}" +%s 2>/dev/null || echo 0)
NOW_TS=$(date +%s)

if [ "${EXPIRY_TS}" -eq 0 ]; then
    echo "[$(date -u -Iseconds)] ssl-check ABORT: cannot parse expiry '${EXPIRY_DATE}'" >&2
    exit 2
fi

DAYS_LEFT=$(( (EXPIRY_TS - NOW_TS) / 86400 ))

if [ "${DAYS_LEFT}" -lt 0 ]; then
    echo "[$(date -u -Iseconds)] ssl-check CRITICAL: certificate EXPIRED ${DAYS_LEFT#-} days ago (${EXPIRY_DATE})" >&2
    exit 1
fi

if [ "${DAYS_LEFT}" -le "${SSL_EXPIRY_WARN_DAYS}" ]; then
    echo "[$(date -u -Iseconds)] ssl-check WARN: certificate expires in ${DAYS_LEFT} days (${EXPIRY_DATE})" >&2
    exit 1
fi

echo "[$(date -u -Iseconds)] ssl-check OK: ${DAYS_LEFT} days remaining (${EXPIRY_DATE})"
exit 0
