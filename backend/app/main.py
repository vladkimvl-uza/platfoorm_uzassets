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

    # Pack 12.1: start in-process webhook delivery worker
    try:
        from app.services.webhook_worker import start_worker as start_wh_worker
        start_wh_worker()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Webhook worker start failed: {e}")

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
    # Best-effort engine disposal (engine may live in different modules)
    for _engine_path in (
        "app.core.database.engine",
        "app.database.engine",
        "app.db.session.engine",
    ):
        try:
            mod_path, attr = _engine_path.rsplit(".", 1)
            engine = getattr(importlib.import_module(mod_path), attr, None)
            if engine is not None and hasattr(engine, "dispose"):
                await engine.dispose()
                break
        except Exception:
            continue


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ App ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
app = FastAPI(
    title="UzAssets Platform API",
    version="0.5.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ CORS ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ╨а╨Ж╨▓╨В╤Ь╨атАЪ
_origins: list[str] = ["*"]
if _settings is not None:
    if hasattr(_settings, "cors_origins_list"):
        _origins = list(_settings.cors_origins_list)
    elif hasattr(_settings, "CORS_ORIGINS"):
        _origins = list(_settings.CORS_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    "auth",
    "auth_mfa",  # Pack 13.0c
    "admin_mfa",  # Pack 13.1.2
    "bot_callbacks",  # Pack 13.2
    "rbac_v3",          # Единый RBAC (заменяет старые rbac.py и rbac_v2.py)
    "companies",
    "projects",
    "tasks",
    "comments",
    "ratings",
    "dashboard",
    "executive_dashboard",
    "financials",
    "finmodel_storage",
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
    "webhooks",            # Pack 12.1 - Webhook subscriptions + delivery log
    "external_apis",       # Pack 12.2 - External APIs registry + OpenAPI upload
    "partners",            # Pack 12.4 - Integration partners (umbrella orgs)
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
