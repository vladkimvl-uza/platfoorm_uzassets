#!/usr/bin/env bash
# Install crontab from BACKUP_SCHEDULE, run an initial backup, then exec crond.
set -euo pipefail
: "${BACKUP_SCHEDULE:=0 */6 * * *}"

# Persist environment so cron-launched scripts can see POSTGRES_* + BACKUP_*.
env | grep -E '^(POSTGRES_|BACKUP_|TZ=)' > /etc/environment

# Wrapper that loads /etc/environment before running backup.
cat > /usr/local/bin/cron-backup <<'EOF'
#!/usr/bin/env bash
set -a; . /etc/environment; set +a
/usr/local/bin/backup.sh >> /var/log/backup.log 2>&1
EOF
chmod +x /usr/local/bin/cron-backup

mkdir -p /var/log /var/spool/cron/crontabs
{
    echo "${BACKUP_SCHEDULE} /usr/local/bin/cron-backup"
    # SSL certificate expiry daily check (07:00 UTC)
    if [ -x /usr/local/bin/check-ssl-expiry.sh ]; then
        echo "0 7 * * * /usr/local/bin/check-ssl-expiry.sh >> /var/log/ssl-check.log 2>&1"
    fi
} > /var/spool/cron/crontabs/root

echo "[$(date -u -Iseconds)] uza-backup starting, schedule=${BACKUP_SCHEDULE}"
echo "[$(date -u -Iseconds)] running initial backup on boot…"
/usr/local/bin/backup.sh || echo "[$(date -u -Iseconds)] initial backup failed (will retry on schedule)"

# crond -f runs in foreground; -d 8 = log to stderr with low verbosity.
exec crond -f -d 8
