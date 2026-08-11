"""Настраиваемая политика модерации (принцип владельца «всё настраиваемо», Фаза 3).

Какие МОДУЛИ модерируются — теперь не хардкод-фрозсет, а конфиг в system_config
(ключ ``moderation.policy``), редактируемый из панели (Фаза 5).

Разведение «политика vs капабилити»:
  • КАПАБИЛИТИ (в коде, в UI НЕ выносится): какие модули ВООБЩЕ можно
    модерировать = архитектурный потолок ``LOCKED_MODERATABLE`` И бакет A
    (`moderation_routes.MODERATABLE_MODULES`) И у модуля есть зарегистрированный
    apply-хендлер. Нельзя дать админу включить модуль без хендлера (одобрение
    уйдёт в skip → потеря данных) или системный роут (чикен-эгг).
  • ПОЛИТИКА (в конфиге, из UI): какие из доступных модулей реально включены.

АРХИТЕКТУРНОЕ РЕШЕНИЕ (владелец, авг 2026): модерируется ТОЛЬКО работа с
проектами и задачами. Всё остальное всегда применяется напрямую (открыто), а
подотчётность обеспечивает журнал изменений (кто/что/когда). Поэтому потолок
жёстко ограничен ``{"tasks", "projects"}`` — панель физически не может включить
ничего сверх, даже если в конфиге остались старые модули.

Дефолт (если конфига ещё нет) — весь разрешённый набор (tasks + projects ВКЛ).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

_KEY = "moderation.policy"
_TTL = 20.0  # сек: политика меняется редко — не дёргаем БД на каждую запись

# Архитектурный потолок модерируемых модулей. Модерация допустима ТОЛЬКО для
# работы с проектами и задачами; всё прочее открыто (см. модуль-docstring).
# Это НЕ настраиваемо из UI — жёсткая граница возможностей.
LOCKED_MODERATABLE = frozenset({"tasks", "projects"})

# Версия политики. При смене архитектуры (переход на tasks/projects-only) старый
# allow-list в БД (пустой или со старыми модулями) нормализуется ОДИН раз к новому
# дефолту — см. normalize_policy(). Дальше правки админа из панели уважаются.
_POLICY_VERSION = 2

# in-process TTL-кэш (по воркеру; eventual consistency для конфига приемлема)
_cache: dict[str, Any] = {"at": 0.0, "modules": None}


def _handler_modules() -> set[str]:
    """Модули с зарегистрированным apply-хендлером (иначе одобрение → skip)."""
    from app.services.moderation_service import APPLY_HANDLERS
    return set(APPLY_HANDLERS.keys())


def moderatable_modules() -> set[str]:
    """Что ВООБЩЕ можно включить в модерацию: архитектурный потолок
    (tasks/projects) И бакет A И есть apply-хендлер."""
    from app.core.moderation_routes import MODERATABLE_MODULES
    return set(MODERATABLE_MODULES) & _handler_modules() & set(LOCKED_MODERATABLE)


async def _load(db: AsyncSession) -> set[str]:
    from app.repositories.snapshot_store import SnapshotStore
    raw = await SnapshotStore(db).load(_KEY)
    avail = moderatable_modules()
    # Храним ВКЛЮЧЁННЫЕ (allow-list); всегда пересекаем с доступными (потолок
    # tasks/projects) — старые модули в конфиге автоматически отбрасываются.
    if isinstance(raw, dict) and isinstance(raw.get("enabled_modules"), list):
        return {str(m) for m in raw["enabled_modules"]} & avail
    # Нет конфига → модерируем весь разрешённый набор (tasks + projects) из коробки.
    return set(avail)


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
    """Политика для панели. По новой архитектуре модерируемы ТОЛЬКО tasks/projects
    (см. LOCKED_MODERATABLE), поэтому доступный набор — эти два модуля; остальные
    в панель не выносятся (всё прочее всегда открыто)."""
    enabled = await get_enabled_modules(db, force=True)
    avail = moderatable_modules()
    return {
        "enabled_modules": sorted(enabled),
        "available_modules": sorted(avail),
        "moderatable_all": sorted(LOCKED_MODERATABLE),
        # Модули в пределах потолка, но без apply-хендлера (в норме пусто —
        # у tasks/projects хендлеры есть). Не выносим сюда открытые модули.
        "needs_handler": sorted(set(LOCKED_MODERATABLE) - avail),
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
        _KEY, {"enabled_modules": enabled, "policy_version": _POLICY_VERSION},
        "Политика модерации: включённые модули (панель)",
    )
    _cache["modules"] = set(enabled)
    _cache["at"] = time.monotonic()
    return {"enabled_modules": enabled, "rejected": rejected}


async def normalize_policy(db: AsyncSession) -> None:
    """Одноразовая нормализация при переходе на архитектуру tasks/projects-only.

    Старый конфиг (без ``policy_version`` или с прежней версией) мог быть пустым
    (deny-by-default rollout) или содержать модули вне нового потолка. Приводим его
    к новому дефолту (весь разрешённый набор = tasks + projects ВКЛ) РОВНО ОДИН
    раз и штампуем версию. После этого правки админа из панели (которые пишут
    актуальную версию) не трогаются. Идемпотентно: при совпадении версии — no-op.
    """
    from app.repositories.snapshot_store import SnapshotStore
    store = SnapshotStore(db)
    raw = await store.load(_KEY)
    version = raw.get("policy_version") if isinstance(raw, dict) else None
    if version == _POLICY_VERSION:
        return
    default_enabled = sorted(moderatable_modules())  # {tasks, projects}
    if not default_enabled:
        # Потолок пуст — значит apply-хендлеры tasks/projects не импортнулись.
        # НЕ штампуем версию (иначе version-gate навсегда закрепит выключенную
        # модерацию без самопочинки) — попробуем снова на следующем старте.
        log.error(
            "normalize_policy: moderatable set empty (tasks/projects apply-handlers "
            "failed to import?) — политика не нормализована, повтор при след. старте",
        )
        return
    await store.save(
        _KEY, {"enabled_modules": default_enabled, "policy_version": _POLICY_VERSION},
        "Нормализация политики модерации → только проекты и задачи",
    )
    invalidate_cache()
