FROM python:3.12-slim

WORKDIR /app

# System dependencies
# - fonts-dejavu-core: required by app.services.tg_banner (Cyrillic glyphs
#   for Telegram banner generation — without this, рендер кириллицы дает □□□)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    fonts-dejavu-core \
    certbot \
    && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1001 uza \
 && useradd --system --uid 1001 --gid uza --home-dir /app --shell /usr/sbin/nologin uza

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create writable dirs and chown app tree to the non-root user.
RUN mkdir -p /app/uploads /app/keys /app/var \
 && chown -R uza:uza /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER uza

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips=*"]
