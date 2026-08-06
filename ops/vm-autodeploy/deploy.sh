#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Pull-based deploy for the UzAssets platform.
#
# WHY: inbound SSH (port 22) on the VM is periodically firewalled (packets
# dropped), which blocks the usual push-based deploy. The VM's OUTBOUND access
# to github.com:443 works, so the VM pulls changes itself — no inbound port
# needed. Run on a schedule by the systemd timer, or manually any time.
#
# Idempotent: exits early if origin/master == local HEAD (no rebuild).
# Safe: preserves the environment-specific jwt_public.pem across git reset.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="${UZA_REPO:-/home/ubuntu/platfoorm_uzassets}"
BRANCH="${UZA_BRANCH:-master}"
COMPOSE_FILE="backend/docker-compose.yml"
PROFILE="production"
LOG="${UZA_DEPLOY_LOG:-/home/ubuntu/uza-autodeploy.log}"

log() { echo "$(date -Is) $*" | tee -a "$LOG"; }

cd "$REPO"

# Preserve env-specific public key — git reset must not clobber it
# (see memory: jwt_public_key_deploy_gotcha → "Signature verification failed").
KEY="backend/jwt_public.pem"
KEY_BAK="/tmp/uza_jwt_public.pem.bak"
[ -f "$KEY" ] && cp -f "$KEY" "$KEY_BAK" || true

git fetch --quiet origin "$BRANCH"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
  # Quiet on the timer; only log when something actually happened.
  [ "${UZA_VERBOSE:-0}" = "1" ] && log "up-to-date ($LOCAL)"
  exit 0
fi

log "deploying ${LOCAL:0:9} -> ${REMOTE:0:9}"
git reset --hard "origin/$BRANCH"

# Restore the key if the reset removed/changed it
if [ -f "$KEY_BAK" ]; then cp -f "$KEY_BAK" "$KEY"; fi

dc() { docker compose --project-directory . -f "$COMPOSE_FILE" --profile "$PROFILE" "$@"; }

log "rebuilding nginx (frontend) ..."
dc build nginx
log "recreating nginx ..."
dc up -d --force-recreate nginx
log "restarting backend (runtime migrations + seeds) ..."
dc restart backend
# Telegram-бот удалён 05.08.2026 — сервиса больше нет в compose.
# --remove-orphans убирает оставшийся от прежних выкатов контейнер uza-tg-bot.
log "removing orphan containers ..."
dc up -d --remove-orphans

log "deployed ${REMOTE:0:9} OK"
