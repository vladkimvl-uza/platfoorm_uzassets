"""Admin API для настройки SMTP / email-уведомлений.

Позволяет задавать SMTP-параметры из UI (хранятся в system_config, кэш в
памяти) без передеплоя. Гейт: admin.users или OWNER. Пароль наружу не
отдаётся (только флаг наличия).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.i18n import current_locale, locale_of_user, tr
from app.core.security import has_effective_permission
from app.models.user import User
from app.services.email.runtime_config import masked_view, save_to_db
from app.services.email.service import send_generic_email

router = APIRouter(prefix="/email-settings", tags=["email-settings"])


async def _require_admin(db: AsyncSession, user: User) -> None:
    if user.is_owner or await has_effective_permission(db, user, "admin.users"):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Требуется право admin.users или статус OWNER",
    )


class EmailSettingsPayload(BaseModel):
    SMTP_ENABLED: Optional[bool] = None
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None    # пустой/None = не менять
    SMTP_FROM: Optional[str] = None
    SMTP_USE_TLS: Optional[bool] = None
    SMTP_USE_SSL: Optional[bool] = None
    SMTP_VERIFY_CERT: Optional[bool] = None
    PUBLIC_URL: Optional[str] = None


@router.get("")
async def get_email_settings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(db, user)
    return masked_view()


@router.put("")
async def update_email_settings(
    payload: EmailSettingsPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require_admin(db, user)
    await save_to_db(db, payload.model_dump(exclude_none=True))
    return masked_view()


@router.post("/test")
async def send_test_email(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отправить тестовое письмо на email текущего администратора."""
    await _require_admin(db, user)
    locale = locale_of_user(user)
    ok = await send_generic_email(
        to=user.email,
        eyebrow=tr("Проверка", locale),
        title=tr("Тестовое письмо UzAssets", locale),
        body_lines=[
            tr("Это тестовое письмо из интерфейса настройки почты.", locale),
            tr("Если вы его получили — SMTP настроен корректно, уведомления будут доставляться.", locale),
        ],
        locale=locale,
    )
    if not ok:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST,
            tr(
                "Не удалось отправить письмо. Проверьте, что SMTP включён и параметры верны (детали — в логах backend).",
                current_locale(),
            ),
        )
    return {"sent": True, "to": user.email}
