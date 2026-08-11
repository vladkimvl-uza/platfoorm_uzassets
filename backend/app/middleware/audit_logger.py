"""Audit logging middleware (Pack 9.0).

Wraps every HTTP request and writes a single audit_log row after the response.
Skips noisy endpoints (health, audit stream, static, OPTIONS preflights).
Auth user extracted from request.state.user if upstream auth dep set it,
otherwise from the bearer token directly.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import AsyncSessionLocal
from app.services.audit_service import (
    action_from_method,
    module_from_path,
    write_event,
)

logger = logging.getLogger(__name__)

# Path prefixes excluded from logging — high-volume / internal / не-действия.
SKIP_PREFIXES = (
    "/healthz",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon",
    "/presence",               # heartbeat присутствия (каждые 45с) — не действие, флудит аудит
    "/auth/refresh",           # авто-обновление токена сессии — не действие пользователя
    "/notifications",          # чтение/пометка/поллинг уведомлений — не взаимодействие с модулем
    "/watches",                # подписка/отписка на проекты/задачи — служебное
    "/comments",               # комментарии пишут собственный rich-аудит (comment.*)
    "/status-updates",         # ход проекта пишет собственный rich-аудит (status_update.*)
    "/ai/chat",                # ИИ-чат пишет собственный rich-аудит (ai.query) с текстом запроса
    "/admin/audit",            # сам аудит (просмотр/экспорт) — не пишем рекурсивно
)

# Аудит отражает изменения данных + security-события (вход/выход) + ПРОСМОТРЫ
# чувствительных разделов (149 п.6.7d — журналирование просмотра и изменения
# данных). preflight (OPTIONS/HEAD) — не взаимодействие, не пишем.
_AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Чувствительные разделы, чьи ПРОСМОТРЫ (GET) тоже журналируются — с троттлингом
# (один просмотр раздела на пользователя раз в _VIEW_THROTTLE_SECONDS), чтобы не
# флудить аудит. /admin/audit исключён через SKIP_PREFIXES (без рекурсии).
_VIEW_AUDIT_PREFIXES = (
    "/companies", "/company", "/financials", "/bp", "/kpi", "/governance",
    "/esg", "/procurement", "/forensic", "/consultants", "/ratings",
    "/users", "/rbac", "/admin", "/invest", "/credit", "/export",
)
_VIEW_THROTTLE_SECONDS = 300
_VIEW_SEEN_CAP = 5000
_view_seen: dict[str, float] = {}


def _view_key(actor_id: Optional[str], path: str) -> str:
    """Ключ троттлинга = пользователь + полный путь (без query). Каждый отдельный
    ресурс журналируется раз в окно, а повторные открытия того же — гасятся."""
    return f"{actor_id or '-'}::{path.split('?')[0]}"


def _view_throttled(actor_id: Optional[str], path: str) -> bool:
    key = _view_key(actor_id, path)
    now = time.monotonic()
    last = _view_seen.get(key)
    if last is not None and now - last < _VIEW_THROTTLE_SECONDS:
        return True
    if len(_view_seen) > _VIEW_SEEN_CAP:
        _view_seen.clear()
    _view_seen[key] = now
    return False


def _should_skip(path: str, method: str) -> bool:
    m = method.upper()
    if any(path.startswith(p) for p in SKIP_PREFIXES):
        return True
    if m in _AUDIT_METHODS:                # изменения — пишем
        return False
    if m == "GET":                         # просмотры — только чувствительные разделы
        return not any(path.startswith(p) for p in _VIEW_AUDIT_PREFIXES)
    return True                            # HEAD/OPTIONS — пропускаем


async def _extract_user(request: Request) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Get (actor_id, actor_email, actor_role) from request.state if available."""
    user = getattr(request.state, "user", None)
    if user is None:
        return None, None, None
    try:
        actor_id = str(user.id) if getattr(user, "id", None) else None
        email = getattr(user, "email", None)
        role = None
        roles = getattr(user, "roles", None)
        if roles and len(roles) > 0:
            r0 = roles[0]
            role = getattr(r0, "code", None) or getattr(r0, "name", None)
        return actor_id, email, role
    except Exception:
        return None, None, None


class AuditLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        method = request.method

        if _should_skip(path, method):
            return await call_next(request)

        start = time.perf_counter()
        status = 500
        response: Optional[Response] = None
        try:
            response = await call_next(request)
            status = response.status_code
            # Обогащение фида активности: при POST-создании название новой записи
            # существует только в ОТВЕТЕ (в пути id ещё нет, тело может не нести
            # name/title) → без этого уведомление читается как безликое «Добавил
            # запись». Снимаем небольшое JSON-тело ответа, достаём человекочитаемое
            # название (whitelist-ключи, рекурсия) и пересобираем Response 1:1.
            # Строго best-effort: любые сбои — игнор, ответ не трогаем.
            if (
                method.upper() == "POST"
                and 200 <= status < 300
                and getattr(request.state, "activity_descriptor", None) is None
                and getattr(request.state, "activity_entity", None) is None
            ):
                try:
                    ctype = (response.headers.get("content-type") or "").lower()
                    clen = int(response.headers.get("content-length") or "0")
                    if "application/json" in ctype and 0 < clen <= 32768:
                        body_bytes = b"".join(
                            [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
                        )
                        rebuilt = Response(
                            content=body_bytes,
                            status_code=status,
                            headers=dict(response.headers),
                            media_type=response.media_type,
                        )
                        response = rebuilt
                        import json as _json

                        from app.services.owner_activity import extract_descriptor
                        desc = extract_descriptor(_json.loads(body_bytes))
                        if desc:
                            request.state.activity_descriptor = desc
                except Exception:  # noqa: BLE001 — не ломаем ответ ради детали фида
                    pass
        except Exception:
            status = 500
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)

            # Audit write — never use `return` inside a `finally`, it overrides
            # the request's response with None and breaks downstream middleware.
            try:
                action = action_from_method(method, status)
                module = module_from_path(path)
                actor_id, actor_email, actor_role = await _extract_user(request)

                # Skip unauthenticated views — they're typically pre-auth pings
                should_log = not (
                    actor_email is None and action == "VIEW" and status < 400
                )
                # Просмотры (GET): пишем только успешные, аутентифицированные и
                # не чаще троттла (иначе аудит зальёт повторными открытиями).
                if should_log and method.upper() == "GET":
                    if (
                        actor_email is None
                        or status >= 400
                        or _view_throttled(actor_id, path)
                    ):
                        should_log = False
                if should_log:
                    ip = (request.client.host if request.client else None)
                    ua = request.headers.get("user-agent", "")[:512]
                    is_critical = action == "DELETE" or status >= 500

                    # Impersonation-атрибуция: действие «под чужим аккаунтом» (Войти
                    # как) пишется на actor_id = ЦЕЛЬ; реальный инициатор — в
                    # request.state.impersonator_* (из токена). Дублируем его в NOTES
                    # (notes ВХОДИТ в HMAC-цепь build_chain_body → tamper-evident, не
                    # репудируется) + в meta (структурно, для UI). meta в хеш НЕ
                    # входит, поэтому ответственный держится именно в hashed-notes.
                    _imp_id = getattr(request.state, "impersonator_id", None)
                    _imp_email = getattr(request.state, "impersonator_email", None)
                    audit_meta = None
                    _notes = getattr(request.state, "activity_summary", None)
                    if _imp_id:
                        audit_meta = {"impersonator_id": _imp_id, "impersonator_email": _imp_email}
                        _tag = f"[от имени: {_imp_email or _imp_id}]"
                        _notes = f"{_tag} {_notes}" if _notes else _tag
                    async with AsyncSessionLocal() as db:
                        await write_event(
                            db,
                            actor_id=actor_id,
                            actor_email=actor_email,
                            actor_role=actor_role,
                            action=action,
                            module=module,
                            http_method=method,
                            http_path=path[:512],
                            http_status=status,
                            duration_ms=duration_ms,
                            ip_address=ip,
                            user_agent=ua,
                            is_critical=is_critical,
                            # Роут может положить человекочитаемую деталь в request.state
                            # (напр. /ai/chat — текст запроса к ИИ). Пишем в аудит.
                            entity_label=getattr(request.state, "activity_entity", None),
                            notes=_notes,
                            meta=audit_meta,
                        )
                        await db.commit()

                        # OWNER activity feed: notify owners of meaningful
                        # changes across all companies (status/comments/files/
                        # editor edits). Best-effort, in-app only, throttled.
                        try:
                            from app.services.owner_activity import (
                                notify_owners_of_change,
                            )
                            await notify_owners_of_change(
                                db,
                                http_path=path,
                                http_method=method,
                                status=status,
                                actor_id=actor_id,
                                actor_email=actor_email,
                                # Роут (где известен diff) кладёт список изменённых
                                # полей в request.state; иначе — общий фолбэк из
                                # ключей JSON-тела (capture_activity), чтобы деталь
                                # «что изменено» была по ВСЕМ модулям, не только
                                # задачам/проектам.
                                changed_fields=(
                                    getattr(request.state, "activity_fields", None)
                                    or getattr(request.state, "activity_body_keys", None)
                                ),
                                summary=getattr(request.state, "activity_summary", None),
                                entity_override=getattr(request.state, "activity_entity", None),
                                # Из тела запроса (capture_activity): название записи
                                # и ссылка на компанию — для детали и scope по всем модулям.
                                descriptor=getattr(request.state, "activity_descriptor", None),
                                company_ref=getattr(request.state, "activity_company_ref", None),
                            )
                        except Exception as _oe:
                            logger.warning("owner-activity hook failed: %s", _oe)
            except Exception as e:
                # Never let audit logging break the request path
                logger.warning("audit middleware error: %s", e)

        return response
