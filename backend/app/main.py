"""
FastAPI application entry point.

Routing model
╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
nginx (edge) does NOT rewrite ╨а╨Ж╨атАЪ╨▓╨В╤Ь it reverse-proxies /api/* unchanged to the
backend. Therefore each router must define its own internal prefix
(e.g. APIRouter(prefix="/api/auth", ...)) ╨а╨Ж╨атАЪ╨▓╨В╤Ь main.py mounts it as-is, no
override. Earlier override_prefix="/api" experiments either double-prefixed
(/api/api/auth/login) or broke when nginx config changed.

Loader is defensive: each router is imported via importlib in a try/except
loop, so one broken router never takes down the whole API. Skipped routers
are logged with the reason; mounted routers are logged with their prefix.
"""
from __future__ import annotations

import importlib
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("uzassets")


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ Settings (try multiple known locations) ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
_settings: Any = None
for _path in ("app.config", "app.core.config"):
    try:
        _settings = importlib.import_module(_path).settings
        break
    except (ImportError, AttributeError):
        continue


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ Lifespan ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
@asynccontextmanager
async def lifespan(app: FastAPI):
    env = getattr(_settings, "ENVIRONMENT", "unknown") if _settings else "unknown"
    logger.info(f"UzAssets backend starting | env={env}")

    # Observability — Sentry (errors) + Prometheus (counters). No-op if env
    # vars unset, so dev stays lean.
    try:
        from app.core.observability import init_sentry, init_prometheus
        init_sentry()
        init_prometheus()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Observability init failed: {e}")

    # Pack 7.36: self-healing schema check for Pack 7.35.
    # Idempotent ╨▓╨ВтАЭ auto-applies Pack 7.35 schema (year_registry.uz_budget_trln)
    # if it wasn't applied via alembic. Failure is non-fatal.
    try:
        from app.core.runtime_migrations import ensure_yearly_rates_schema
        await ensure_yearly_rates_schema()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Runtime migration self-heal failed: {e}")

    # Pack 11.2: start in-process broadcast scheduler
    try:
        from app.services.broadcast_scheduler import start_scheduler
        start_scheduler()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Broadcast scheduler start failed: {e}")

    # Pack 150: TLS auto-renewal scheduler (daily check, renew if needed)
    try:
        from app.services.tls_scheduler import start_tls_renewal_scheduler
        start_tls_renewal_scheduler()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"TLS renewal scheduler start failed: {e}")

    # Pack 12.1: start in-process webhook delivery worker
    try:
        from app.services.webhook_worker import start_worker as start_wh_worker
        start_wh_worker()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Webhook worker start failed: {e}")

    # SMTP/email: загрузка рантайм-конфигурации из system_config в кэш.
    try:
        from app.database import AsyncSessionLocal
        from app.services.email.runtime_config import load_from_db as _load_email_cfg
        async with AsyncSessionLocal() as _db:
            await _load_email_cfg(_db)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Email config load failed: {e}")

    # Encryption key startup validation. If any user has mfa_enabled=true
    # we MUST be able to decrypt their TOTP secret — fail fast instead of
    # discovering this at runtime when someone tries to log in.
    try:
        from sqlalchemy import select, func
        from app.database import AsyncSessionLocal
        from app.models.user import User
        async with AsyncSessionLocal() as _db:
            mfa_users = (await _db.execute(
                select(func.count(User.id)).where(User.mfa_enabled.is_(True))
            )).scalar() or 0
        if mfa_users > 0:
            from app.core.encryption import _fernet
            try:
                _fernet()
                logger.info(f"MFA encryption key OK ({mfa_users} MFA users)")
            except Exception as e:
                if env == "production":
                    raise RuntimeError(
                        f"SECURITY FATAL: {mfa_users} users have MFA enabled but "
                        f"encryption key is unavailable: {e}"
                    )
                logger.warning(f"MFA encryption not configured but {mfa_users} users enabled: {e}")
    except RuntimeError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MFA encryption check skipped: {e}")

    # Audit chain hourly background verifier. Detects DB-level tampering.
    try:
        import asyncio
        from app.core.audit_chain import verify_chain
        from app.database import AsyncSessionLocal
        async def _audit_chain_verifier_loop():
            from app.core.observability import gauge_set
            while True:
                try:
                    await asyncio.sleep(3600)  # 1 hour
                    async with AsyncSessionLocal() as _db:
                        res = await verify_chain(_db)
                    if not res.get("ok"):
                        gauge_set("audit_chain_status", 0)
                        gauge_set("audit_chain_rows", res.get("checked", 0))
                        logger.error(
                            f"SECURITY: audit chain broken at row {res.get('broken_at')} "
                            f"(reason={res.get('reason')}) — TAMPERING SUSPECTED"
                        )
                    else:
                        gauge_set("audit_chain_status", 1)
                        gauge_set("audit_chain_rows", res.get("checked", 0))
                        logger.info(f"Audit chain verified OK ({res.get('checked')} rows)")
                except asyncio.CancelledError:
                    return
                except Exception as ex:  # noqa: BLE001
                    logger.warning(f"Audit chain verifier error: {ex}")
        app.state._audit_verifier_task = asyncio.create_task(_audit_chain_verifier_loop())
        logger.info("Audit chain verifier task scheduled (hourly)")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Audit chain verifier task NOT started: {e}")

    yield
    logger.info("UzAssets backend shutting down")

    # Pack 11.2: stop scheduler gracefully
    try:
        from app.services.broadcast_scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass
    # Pack 12.1: stop webhook worker gracefully
    try:
        from app.services.webhook_worker import stop_worker as stop_wh_worker
        await stop_wh_worker()
    except Exception:
        pass
    # Cancel audit chain verifier loop
    try:
        t = getattr(app.state, "_audit_verifier_task", None)
        if t is not None:
            t.cancel()
    except Exception:
        pass
    # 2026-05-26: канонический engine path — `app.database.engine`.
    # Раньше пытались 3 import-path'а (core.database, database, db.session) —
    # legacy от прошлых миграций. Теперь один путь + clean error logging.
    try:
        from app.database import engine
        if engine is not None and hasattr(engine, "dispose"):
            await engine.dispose()
    except Exception as e:
        logger.warning(f"DB engine disposal failed: {e}")


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ App ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
# Disable interactive docs in production — they expose internal field names,
# parameter types, and undocumented endpoints to anonymous reconnaissance.
# Set ENABLE_DOCS_IN_PRODUCTION=true in env to override (e.g. for staging).
_is_prod = _settings is not None and getattr(_settings, "is_production", False)
_docs_in_prod = (os.environ.get("ENABLE_DOCS_IN_PRODUCTION", "false").lower() == "true")
_expose_docs = (not _is_prod) or _docs_in_prod

app = FastAPI(
    title="UzAssets Platform API",
    version="0.5.0",
    lifespan=lifespan,
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
)


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ CORS ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
# Default: deny all (empty list). Wildcard with credentials is a CORS spec
# violation — any origin could make authenticated requests. Explicit list is
# always loaded from settings in real deployments; empty default makes a
# misconfigured deploy fail loud (browser blocks all cross-origin) instead
# of silently allowing the universe.
_origins: list[str] = []
if _settings is not None:
    if hasattr(_settings, "cors_origins_list"):
        _origins = list(_settings.cors_origins_list)
    elif hasattr(_settings, "CORS_ORIGINS"):
        _origins = list(_settings.CORS_ORIGINS)

# Fail-fast: refuse wildcard + credentials in production.
if _settings is not None and getattr(_settings, "is_production", False):
    if "*" in _origins:
        raise RuntimeError(
            "SECURITY FATAL: CORS_ORIGINS contains '*' with allow_credentials=True. "
            "This is a CORS spec violation and will be rejected by browsers. "
            "Set explicit origins in environment."
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Api-Key"],
)

# ─── Defense-in-depth middlewares (audit P2) ─────────────────────────
# Note: Starlette processes middlewares in REVERSE order of registration
# (last added wraps the outermost), so order matters. We want:
#   request → TrustedHost → BodySize → RequestID → CORS → SecurityHeaders → app
# Registration order to achieve this (reversed): SecurityHeaders, CORS (above),
# RequestID, BodySize, TrustedHost (below).
try:
    from app.core.security_middleware import (
        SecurityHeadersMiddleware, RequestIDMiddleware, BodySizeLimitMiddleware,
    )
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    # Apply security headers to all responses (defense-in-depth alongside nginx).
    app.add_middleware(SecurityHeadersMiddleware)
    # Request ID for correlation in logs.
    app.add_middleware(RequestIDMiddleware)
    # Reject oversized bodies at app level (nginx has client_max_body_size 25m).
    app.add_middleware(BodySizeLimitMiddleware)
    # Host header allow-list — rejects evil-host pings.
    _trusted = []
    if _settings is not None and hasattr(_settings, "TRUSTED_HOSTS"):
        _raw = _settings.TRUSTED_HOSTS
        if isinstance(_raw, str):
            _trusted = [h.strip() for h in _raw.split(",") if h.strip()]
        else:
            _trusted = list(_raw)
    if _trusted:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted)
        logger.info(f"TrustedHostMiddleware: {_trusted}")
    else:
        logger.warning("TrustedHostMiddleware NOT registered (no TRUSTED_HOSTS configured)")
    logger.info("Defense-in-depth middlewares registered (SecurityHeaders, RequestID, BodySize, TrustedHost)")
except Exception as e:
    logger.warning(f"Defense-in-depth middlewares not registered: {e}")

# Startup safety check: file permissions + placeholder-key detection.
try:
    import os, stat
    if _settings is not None and getattr(_settings, "is_production", False):
        for key_path in ("/app/keys/jwt_private.pem", "/app/keys/fernet.key", "/app/keys/audit_hmac.key"):
            if os.path.exists(key_path):
                mode = os.stat(key_path).st_mode
                if mode & (stat.S_IRGRP | stat.S_IROTH):
                    logger.error(
                        f"SECURITY: {key_path} is readable by group/other (mode={oct(mode)}). "
                        f"Run: chmod 600 {key_path} on the Linux host."
                    )
        # Placeholder-key detection — refuse to start prod with the dev-default
        # 128 × "0" audit HMAC secret. The file is shipped as a placeholder so
        # generate-keys.sh MUST be run before production deployment.
        audit_key_path = "/app/keys/audit_hmac.key"
        if os.path.exists(audit_key_path):
            with open(audit_key_path, "rb") as f:
                content = f.read().strip()
            if content == b"0" * len(content) or len(content) < 32:
                raise RuntimeError(
                    f"SECURITY FATAL: {audit_key_path} is a placeholder ({len(content)} bytes of 0). "
                    "Run scripts/generate-keys.sh to generate real secrets before starting in production."
                )
except RuntimeError:
    raise
except Exception:
    pass


# slowapi global rate limiter — auth bucket (10/min) is per-route via decorator.
try:
    from app.core.rate_limit import limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("slowapi rate limiter installed (app.state.limiter)")
except Exception as e:
    logger.warning(f"slowapi rate limiter not registered: {e}")


# Centralized exception taxonomy + 5xx Telegram alerter.
# Handlers: AppError → typed JSON, HTTPException → pass-through (alert if 5xx),
# Exception → 500 + TG alert. Order matters — register AFTER slowapi so its
# RateLimitExceeded handler keeps priority.
try:
    from app.core.error_handlers import register_error_handlers
    register_error_handlers(app)
    logger.info("Error handlers registered (AppError taxonomy + 5xx TG alerter)")
except Exception as e:
    logger.warning(f"Error handlers not registered: {e}")


# ╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В Audit logging middleware (Pack 9.0) ╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В╨▓тАЭ╨В
# Wraps every request and writes one audit_log row per response.
# Must be registered AFTER CORS so OPTIONS pre-flight is skipped.
try:
    from app.middleware.audit_logger import AuditLoggerMiddleware
    app.add_middleware(AuditLoggerMiddleware)
    logger.info("Audit middleware registered")
except Exception as e:
    logger.warning(f"Audit middleware not registered: {e}")


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ Router registration ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
# All routers are loaded from app.api.routes.{name}.
# Mount with NO prefix override ╨а╨Ж╨атАЪ╨▓╨В╤Ь each router carries its own internal prefix.
ROUTER_MODULES = [
    "mfa",
    "health",
    "metrics",        # Pack 148 P2-12: Prometheus /metrics (Basic auth)
    "attachments",    # Pack 149: file uploads (task/project/company) + S3 backend
    "user_search",    # Pack 149: lightweight /users/search for autocomplete + @-mention
    "company_activity",  # Pack 149: per-company activity feed for workspace widget
    "storage_admin",     # Pack 149: storage backend status + smoke test (S3/local)
    "auth",
    "auth_mfa",  # Pack 13.0c
    "admin_mfa",  # Pack 13.1.2
    "db_admin",   # Pack 149 — DB console for is_owner/is_admin
    "tls_admin",  # Pack 150 — TLS cert management (Let's Encrypt + manual upload)
    "forgot_password",  # Pack 152 — forgot-password via Telegram-code
    "bot_callbacks",  # Pack 13.2
    "tg_banners",     # Pack 147 / Phase B — Telegram banner images
    "rbac_v3",          # Единый RBAC (заменяет старые rbac.py и rbac_v2.py)
    "companies",
    "projects",
    "tasks",
    "comments",
    "ratings",
    "dashboard",
    "executive_dashboard",
    "monitoring",       # Контрольная вышка — период-агрегация прогресса
    "financials",
    # "finmodel_storage" — v1 удалён (Phase 0 finmodel-v2-handoff)
    "finmodel",        # v2 (Phase 1)
    "invest_projects",
    "credit_portfolio",
    "procurement_analysis",
    "boards",         # may not exist yet -- gracefully skipped if missing
    "business_plan",  # requires app.api.deps
    "kpi",            # requires app.api.deps
    "esg",            # requires app.models.esg (existing from Phase 3b)
    "governance",     # requires app.models.governance (existing from Phase 3b)
    "consultants",
    "directions",
    "forensic",      # Forensic & Procurement audit page (Phase 8)
    "notes",            # Smart Journal (Phase 8)
    "ai",               # Pack 7.1 - AI Assistant
    "system_config",    # Pack 7.35 - admin UI for yearly rates / UZ budget
    "scenarios",       # Pack 7.40 - macro scenarios
    "credit_scenario",  # Pack 7.41
    "elasticity",      # Pack 7.43
    "audit",            # Pack 9.0 - Audit log + RBAC
    "companies_admin_v2",  # Pack 9.2 - Companies & Sectors advanced (colors, badges, year overrides)
    "notifications",       # Pack 11.0 - In-app notifications, WebSocket, preferences
    "moderation",          # Pack 11.1 - Moderation submissions, rules, queue
    "admin_broadcasts",    # Pack 11.2 - Admin broadcasts (scheduled, sticky, ack)
    "api_catalog",         # Pack 12.0 - Dynamic API catalog + OpenAPI exports
    "api_keys",            # Pack 12.0 - Service accounts + API keys CRUD
    "company_library",     # Pack 9aJ - Company Library MDM + WebSocket sync
    "webhooks",            # Pack 12.1 - Webhook subscriptions + delivery log
    "external_apis",       # Pack 12.2 - External APIs registry + OpenAPI upload
    "partners",            # Pack 12.4 - Integration partners (umbrella orgs)
    "email_settings",      # SMTP / email-уведомления (admin-настройка)
]

mounted: list[str] = []
skipped: list[tuple[str, str]] = []

for _name in ROUTER_MODULES:
    try:
        _mod = importlib.import_module(f"app.api.routes.{_name}")
        _router = getattr(_mod, "router", None)
        if _router is None:
            skipped.append((_name, "no `router` attribute"))
            logger.info(f"  [SKIP] app.api.routes.{_name} -- no router attribute")
            continue
        # NATIVE prefix only -- no /api override.
        app.include_router(_router)
        prefix = _router.prefix or "<root>"
        mounted.append(_name)
        logger.info(f"  [OK]   app.api.routes.{_name} (prefix={prefix})")
    except ModuleNotFoundError as e:
        skipped.append((_name, f"ModuleNotFound: {e.name}"))
        logger.info(f"  [SKIP] app.api.routes.{_name} -- ModuleNotFound: {e.name}")
    except Exception as e:
        skipped.append((_name, f"{type(e).__name__}: {e}"))
        logger.exception(f"  [SKIP] app.api.routes.{_name} -- {type(e).__name__}: {e}")

logger.info(f"Routers: {len(mounted)} mounted, {len(skipped)} skipped")
for name, reason in skipped:
    logger.info(f"  skipped: {name} -- {reason}")

# Pack 11.2: mount the second router from admin_broadcasts (recipient-facing /broadcasts/*)
try:
    from app.api.routes.admin_broadcasts import user_router as _broadcasts_user_router
    app.include_router(_broadcasts_user_router)
    logger.info("  [OK]   app.api.routes.admin_broadcasts.user_router (prefix=/broadcasts)")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"  [SKIP] broadcasts user_router: {_e}")

# Pack 9aJ — Company Library MDM WebSocket routes (/ws/companies, /ws/companies/{id})
try:
    from app.api.routes.company_library import ws_router as _library_ws_router
    app.include_router(_library_ws_router)
    logger.info("  [OK]   app.api.routes.company_library.ws_router (WebSocket /ws/companies)")
except Exception as _e:  # noqa: BLE001
    logger.warning(f"  [SKIP] company_library ws_router: {_e}")


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ Top-level endpoints ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
@app.get("/")
async def root():
    return {
        "name": "UzAssets Platform API",
        "version": "0.5.0",
        "docs": "/docs",
        "routers_mounted": len(mounted),
        "routers_skipped": len(skipped),
    }


@app.get("/__alive__")
async def alive():
    """Lightweight liveness check ╨а╨Ж╨атАЪ╨▓╨В╤Ь no DB. Use the health router for full check."""
    return {"status": "ok"}
