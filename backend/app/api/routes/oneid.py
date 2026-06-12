"""ЕСИ / One ID endpoints — тонкий HTTP-шим над services/oneid_service.

Скаффолд: при ONEID_ENABLED=false все боевые эндпоинты возвращают 503.
Текущий вход по логину/паролю не затрагивается.

  GET /auth/oneid/status   — состояние интеграции (включена ли, без секретов)
  GET /auth/oneid/login    — редирект на страницу One ID
  GET /auth/oneid/callback — обработка ?code&state → выпуск JWT → редирект на фронт
"""
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.config import settings
from app.database import get_db
from app.services import oneid_service

router = APIRouter(prefix="/auth/oneid", tags=["auth", "oneid"])


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/status")
async def status_() -> dict:
    """Диагностика: включена ли интеграция ЕСИ (без раскрытия секретов)."""
    return {
        "enabled": settings.ONEID_ENABLED,
        "configured": bool(settings.ONEID_CLIENT_ID and settings.ONEID_CLIENT_SECRET),
        "auto_provision": settings.ONEID_AUTO_PROVISION,
        "authorize_url": settings.ONEID_AUTHORIZE_URL if settings.ONEID_ENABLED else None,
    }


@router.get("/login")
async def login() -> RedirectResponse:
    """Редирект пользователя на страницу аутентификации One ID."""
    return RedirectResponse(oneid_service.build_login_url(), status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """One ID redirect_uri: обмен кода → выпуск JWT → редирект на фронт с токенами.

    Токены передаются во фрагменте URL (#access=...&refresh=...), который не
    попадает в логи сервера/прокси. Фронтенд-обработчик маршрута
    ONEID_FRONTEND_CALLBACK сохраняет их и завершает вход (UI добавляется
    отдельно — это backend-скаффолд)."""
    user, access, refresh = await oneid_service.handle_callback(
        db,
        code=code,
        state=state,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    target = f"{settings.PLATFORM_URL}{settings.ONEID_FRONTEND_CALLBACK}#access={access}&refresh={refresh}"
    return RedirectResponse(target, status_code=302)
