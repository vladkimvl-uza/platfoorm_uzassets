"""Рантайм-конфигурация SMTP (БД + кэш в памяти).

Настройки SMTP можно менять из админ-UI без передеплоя: они хранятся в
`system_config` (ключ `email_settings`) и кэшируются в памяти процесса.
`send_email` читает эффективную конфигурацию из кэша (значения env — дефолт).
Кэш загружается на старте приложения и обновляется при сохранении из UI.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.system_config import SystemConfig

log = logging.getLogger(__name__)

_KEY = "email_settings"
_RUNTIME: dict[str, Any] = {}

# Конфигурируемые поля (имена совпадают с Settings и UI).
FIELDS = (
    "SMTP_ENABLED", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
    "SMTP_FROM", "SMTP_USE_TLS", "SMTP_USE_SSL", "SMTP_VERIFY_CERT", "PUBLIC_URL",
)


def _env_defaults() -> dict[str, Any]:
    return {f: getattr(settings, f) for f in FIELDS}


def effective() -> dict[str, Any]:
    """Env-дефолты, перекрытые рантайм-значениями из БД/UI."""
    cfg = _env_defaults()
    for k, v in _RUNTIME.items():
        if v is not None:
            cfg[k] = v
    return cfg


def apply(cfg: dict[str, Any]) -> None:
    for f in FIELDS:
        if f not in cfg or cfg[f] is None:
            continue
        # Пустой ПАРОЛЬ из UI = «не менять». Остальные поля можно очищать "" —
        # напр. SMTP_USER="" для анонимного релея (Exchange без авторизации).
        if f == "SMTP_PASSWORD" and cfg[f] == "":
            continue
        _RUNTIME[f] = cfg[f]


async def load_from_db(session: AsyncSession) -> None:
    try:
        row = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == _KEY)
        )).scalar_one_or_none()
        if row and isinstance(row.value, dict):
            apply(row.value)
            log.info("email config loaded from DB (enabled=%s host=%s)",
                     effective().get("SMTP_ENABLED"), effective().get("SMTP_HOST"))
    except Exception:  # noqa: BLE001 — старт не должен падать из-за конфига
        log.warning("failed to load email config from DB", exc_info=True)


async def save_to_db(session: AsyncSession, cfg: dict[str, Any]) -> None:
    """Сохранить настройки. Пустой SMTP_PASSWORD = оставить прежний."""
    row = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == _KEY)
    )).scalar_one_or_none()
    clean: dict[str, Any] = {}
    for f in FIELDS:
        if f not in cfg or cfg[f] is None:
            continue
        if f == "SMTP_PASSWORD" and cfg[f] == "":
            continue  # не перезаписывать пароль пустым значением
        clean[f] = cfg[f]
    if row:
        row.value = {**(row.value or {}), **clean}
    else:
        row = SystemConfig(
            key=_KEY, value=clean,
            description="SMTP / email настройки (заданы из админ-UI)",
            is_secret=True,
        )
        session.add(row)
    await session.commit()
    apply(clean)


def masked_view() -> dict[str, Any]:
    """Конфигурация для UI: пароль не отдаём, только флаг наличия."""
    cfg = effective()
    out = {f: cfg.get(f) for f in FIELDS if f != "SMTP_PASSWORD"}
    out["SMTP_PASSWORD_SET"] = bool(cfg.get("SMTP_PASSWORD"))
    return out
