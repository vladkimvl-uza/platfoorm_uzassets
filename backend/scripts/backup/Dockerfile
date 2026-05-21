# Backup container — runs pg_dump on a cron schedule, gzips, optionally GPG-encrypts,
# computes SHA-256 manifest, prunes old archives. Profile: production.
FROM postgres:16-alpine

RUN apk add --no-cache bash dcron gnupg coreutils tzdata openssl && \
    mkdir -p /backups /etc/periodic/custom

COPY backup.sh /usr/local/bin/backup.sh
COPY prune.sh  /usr/local/bin/prune.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY check-ssl-expiry.sh /usr/local/bin/check-ssl-expiry.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/prune.sh \
             /usr/local/bin/entrypoint.sh /usr/local/bin/check-ssl-expiry.sh

ENV TZ=Asia/Tashkent
ENV BACKUP_SCHEDULE="0 */6 * * *"
ENV BACKUP_RETENTION_DAYS=30

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
