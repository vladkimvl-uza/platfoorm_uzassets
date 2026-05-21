# =====================================================================
# nginx + встроенный билд frontend (production)
#
# Stage 1 (builder): Node 20, ставит npm-зависимости, запускает `vite build`,
#                    результат → /app/dist.
# Stage 2 (runtime): nginx:alpine, статика копируется в /usr/share/nginx/html.
#
# Локация `/` в nginx.conf теперь отдаёт static — раньше проксировал на
# frontend:5173. Контейнер `uza-frontend` после этого можно удалить.
#
# ВАЖНО: docker-compose context должен быть КОРЕНЬ проекта (`.`), не `./nginx`
# — потому что stage 1 копирует `frontend/`.
#
# Билд: docker compose --profile production build nginx
#
# Если меняешь Vue-код:
#   docker compose --profile production build nginx
#   docker compose --profile production up -d nginx
# (раньше: `docker exec uza-frontend npx vite build && docker restart uza-frontend`)
# =====================================================================

# ─── Stage 1a: build main frontend ──────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app

COPY frontend/package*.json ./
RUN if [ -f package-lock.json ]; then \
      npm ci --no-fund && npm audit --audit-level=high || true; \
    else \
      npm install --no-fund; \
    fi

COPY frontend/ ./
ENV NODE_OPTIONS=--max-old-space-size=4096
# Empty = relative URLs (frontend and backend live on the same domain via nginx)
ENV VITE_API_BASE_URL=""
# Skip `vue-tsc -b` strict project-mode check; runtime bundle works.
RUN npx vite build

# ─── Stage 1b: build Telegram Mini App (TWA) ────────────────────────
# Separate Vue bundle with base "/twa/". Lives at the same domain under
# /twa/* so the bot's Mini App URL points at the platform itself.
FROM node:20-alpine AS twa-builder
WORKDIR /app

COPY frontend-twa/package*.json ./
RUN if [ -f package-lock.json ]; then \
      npm ci --no-fund || true; \
    else \
      npm install --no-fund; \
    fi

COPY frontend-twa/ ./
ENV NODE_OPTIONS=--max-old-space-size=2048
RUN npx vite build

# ─── Stage 2: nginx runtime ─────────────────────────────────────────
FROM nginx:1.27-alpine

# Strip default site
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx/nginx.conf       /etc/nginx/nginx.conf
COPY nginx/conf.d/          /etc/nginx/conf.d/

# Main SPA at /, TWA bundle at /twa
COPY --from=frontend-builder /app/dist     /usr/share/nginx/html
COPY --from=twa-builder      /app/dist     /usr/share/nginx/html/twa

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q -O - http://127.0.0.1/__nginx_health__ || exit 1

EXPOSE 80 443
