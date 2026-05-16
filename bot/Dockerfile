FROM python:3.12-slim

# Minimal — bot doesn't need build tools at runtime since we use pure-python deps
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Healthcheck — file written by worker each loop iteration
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD test -f /tmp/uza-tg-bot-heartbeat && find /tmp/uza-tg-bot-heartbeat -mmin -2 | grep -q heartbeat || exit 1

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-u", "main.py"]
