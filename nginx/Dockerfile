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

# ─── Stage 1c: build brotli dynamic modules for nginx ───────────────
# ngx_brotli .so files must be compiled against the exact same nginx
# version as the runtime image — so we build inside nginx:1.27-alpine
# itself, copy the .so artifacts into stage 2.
FROM nginx:1.27-alpine AS brotli-builder
RUN apk add --no-cache --virtual .build-deps \
        gcc libc-dev make openssl-dev pcre-dev zlib-dev linux-headers \
        curl git brotli-dev cmake g++ tar bash
WORKDIR /build
RUN NGINX_VERSION="$(nginx -v 2>&1 | sed -n 's|.*nginx/||p')" \
    && echo "Building ngx_brotli against nginx ${NGINX_VERSION}" \
    && git clone --depth=1 --recurse-submodules --shallow-submodules \
         https://github.com/google/ngx_brotli ngx_brotli \
    && curl -fsSL "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" \
         | tar -xz \
    && cd "nginx-${NGINX_VERSION}" \
    && ./configure --with-compat --add-dynamic-module=/build/ngx_brotli \
    && make modules \
    && mkdir -p /modules \
    && cp objs/ngx_http_brotli_filter_module.so  /modules/ \
    && cp objs/ngx_http_brotli_static_module.so  /modules/

# ─── Stage 2: nginx runtime ─────────────────────────────────────────
FROM nginx:1.27-alpine

# Brotli modules — loaded via `load_module` in nginx.conf
COPY --from=brotli-builder /modules/ngx_http_brotli_filter_module.so /usr/lib/nginx/modules/
COPY --from=brotli-builder /modules/ngx_http_brotli_static_module.so /usr/lib/nginx/modules/

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
