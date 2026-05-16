"""Bot configuration — reads from environment (same .env as backend)."""
import os
from typing import Optional


def _required(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise RuntimeError(f"Required env var {key} is empty or missing")
    return v


def _build_dsn() -> str:
    """Compose asyncpg DSN from individual env vars (matches backend setup)."""
    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        # Convert sqlalchemy form 'postgresql+asyncpg://...' to plain asyncpg
        dsn = explicit.replace("postgresql+asyncpg://", "postgresql://", 1)
        return dsn
    host = os.getenv("POSTGRES_HOST", "uza-postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "uza")
    pwd  = os.getenv("POSTGRES_PASSWORD", "")
    db   = os.getenv("POSTGRES_DB", "uzassets")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


# ─── Public settings ─────────────────────────────────────────

BOT_TOKEN          = _required("TELEGRAM_BOT_TOKEN")
BOT_USERNAME       = os.getenv("TELEGRAM_BOT_USERNAME", "UzAssets_bot").lstrip("@")
DATABASE_URL       = _build_dsn()
ENCRYPTION_KEY     = _required("MFA_ENCRYPTION_KEY")
OUTBOX_POLL_SEC    = float(os.getenv("OUTBOX_POLL_SEC", "2.0"))
OUTBOX_BATCH_SIZE  = int(os.getenv("OUTBOX_BATCH_SIZE", "10"))
OUTBOX_MAX_RETRIES = int(os.getenv("OUTBOX_MAX_RETRIES", "5"))
PLATFORM_URL       = os.getenv("PLATFORM_URL", "https://platform.uz-assets.uz")
LOG_LEVEL          = os.getenv("BOT_LOG_LEVEL", "INFO").upper()

# Pack 13.2 — moderation callbacks
PLATFORM_API_URL  = os.getenv("PLATFORM_API_URL", PLATFORM_URL.rstrip("/") + "/api")
BOT_CALLBACK_SECRET = os.getenv("BOT_CALLBACK_SECRET", "")
