"""Настраиваемая политика модерации (принцип владельца «всё настраиваемо», Фаза 3).

Какие МОДУЛИ модерируются — теперь не хардкод-фрозсет, а конфиг в system_config
(ключ ``moderation.policy``), редактируемый из панели (Фаза 5).

Разведение «политика vs капабилити»:
  • КАПАБИЛИТИ (в коде, в UI НЕ выносится): какие модули ВООБЩЕ можно
    модерировать = бакет A (`moderation_routes.MODERATABLE_MODULES`) И у модуля
    есть зарегистрированный apply-хендлер. Нельзя дать админу включить модуль без
    хендлера (одобрение уйдёт в skip → потеря данных) или системный роут
    (чикен-эгг).
  • ПОЛИТИКА (в конфиге, из UI): какие из доступных модулей реально включены.

Дефолт (если конфига ещё нет) — все доступные (бакет A с хендлером).
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

_KEY = "moderation.policy"
_TTL = 20.0  # сек: политика меняется редко — не дёргаем БД на каждую запись

# in-process TTL-кэш (по воркеру; eventual consistency для конфига приемлема)
_cache: dict[str, Any] = {"at": 0.0, "modules": None}


def _handler_modules() -> set[str]:
    """Модули с зарегистрированным apply-хендлером (иначе одобрение → skip)."""
    from app.services.moderation_service import APPLY_HANDLERS
    return set(APPLY_HANDLERS.keys())


def moderatable_modules() -> set[str]:
    """Что ВООБЩЕ можно включить в модерацию: бакет A И есть apply-хендлер."""
    from app.core.moderation_routes import MODERATABLE_MODULES
    return set(MODERATABLE_MODULES) & _handler_modules()


async def _load(db: AsyncSession) -> set[str]:
    from app.repositories.snapshot_store import SnapshotStore
    raw = await SnapshotStore(db).load(_KEY)
    avail = moderatable_modules()
    # ВЫКЛ ПО УМОЛЧАНИЮ (решение владельца при первом выкате): без конфига НЕ
    # модерируется НИЧЕГО — админ включает модули по одному из панели (безопасный
    # поэтапный rollout). Храним ВКЛЮЧЁННЫЕ (allow-list); пересекаем с доступными.
    if isinstance(raw, dict) and isinstance(raw.get("enabled_modules"), list):
        return {str(m) for m in raw["enabled_modules"]} & avail
    return set()


async def get_enabled_modules(db: AsyncSession, *, force: bool = False) -> set[str]:
    now = time.monotonic()
    if not force and _cache["modules"] is not None and (now - _cache["at"]) < _TTL:
        return _cache["modules"]
    mods = await _load(db)
    _cache["modules"] = mods
    _cache["at"] = now
    return mods


def invalidate_cache() -> None:
    _cache["modules"] = None
    _cache["at"] = 0.0


async def get_policy(db: AsyncSession) -> dict[str, Any]:
    """Полная политика для панели: включённые + доступные + (для справки) все
    модерируемые бакета A и те, что ждут apply-хендлер (Фаза 4)."""
    from app.core.moderation_routes import MODERATABLE_MODULES
    enabled = await get_enabled_modules(db, force=True)
    avail = moderatable_modules()
    return {
        "enabled_modules": sorted(enabled),
        "available_modules": sorted(avail),
        "moderatable_all": sorted(MODERATABLE_MODULES),
        # Динамически: бакет-A модули БЕЗ apply-хендлера (по мере появления
        # хендлеров список сам сокращается — не зависит от статичного флага).
        "needs_handler": sorted(set(MODERATABLE_MODULES) - avail),
    }


async def set_enabled_modules(
    db: AsyncSession, modules: list[str], *,
    actor_email: str | None = None, actor_id: str | None = None,
) -> dict[str, Any]:
    """Записать список включённых модулей. Молча отбрасываются те, что нельзя
    модерировать (нет хендлера / не бакет A) — их вернём в ``rejected``."""
    avail = moderatable_modules()
    requested = {str(m) for m in (modules or [])}
    enabled = sorted(requested & avail)
    rejected = sorted(requested - avail)
    from app.repositories.snapshot_store import SnapshotStore
    await SnapshotStore(db).save(
        _KEY, {"enabled_modules": enabled},
        "Политика модерации: включённые модули (панель)",
    )
    _cache["modules"] = set(enabled)
    _cache["at"] = time.monotonic()
    return {"enabled_modules": enabled, "rejected": rejected}
