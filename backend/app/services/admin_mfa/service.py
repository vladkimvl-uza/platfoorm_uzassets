"""Admin overview of MFA across all users (Pack 13.1.2).

GET overview — `admin.users`/`admin.security` permission.
POST force-disable — owner-only emergency reset.

Core helpers (`app.services.mfa_service`, `app.core.audit_chain`) NOT touched.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import _user_permission_codes
from app.models.mfa import MfaMethod
from app.models.user import User


log = logging.getLogger(__name__)


class UserMfaRow(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    is_active: bool
    is_owner: bool
    mfa_enabled: bool
    mfa_method: str
    telegram_linked: bool
    telegram_username: Optional[str] = None
    telegram_linked_at: Optional[datetime] = None
    recovery_codes_remaining: int
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None


class MfaOverviewSummary(BaseModel):
    total: int
    mfa_enabled_count: int
    telegram_linked_count: int
    no_2fa_count: int


class MfaOverviewResponse(BaseModel):
    users: list[UserMfaRow]
    summary: MfaOverviewSummary


def _require_admin(user: User) -> None:
    if user.is_owner:
        return
    perms = _user_permission_codes(user)
    if "admin.users" not in perms and "admin.security" not in perms:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Требуется право admin.users или admin.security",
        )


def _require_owner(user: User) -> None:
    if not user.is_owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Только владелец платформы может принудительно отключать 2FA",
        )


def _client_ip(request: Request) -> Optional[str]:
    from app.core.rate_limit import _real_client_ip
    return _real_client_ip(request) or None


def _row(u: User) -> UserMfaRow:
    method = getattr(u, "mfa_method", MfaMethod.NONE)
    if hasattr(method, "value"):
        method = method.value
    from app.services.mfa_service import get_recovery_codes
    codes = get_recovery_codes(u)
    return UserMfaRow(
        id=str(u.id),
        email=u.email,
        full_name=u.full_name,
        username=u.username,
        is_active=bool(u.is_active),
        is_owner=bool(u.is_owner),
        mfa_enabled=bool(getattr(u, "mfa_enabled", False)),
        mfa_method=method or "none",
        telegram_linked=bool(getattr(u, "telegram_chat_id_encrypted", None)),
        telegram_username=getattr(u, "telegram_username", None),
        telegram_linked_at=getattr(u, "telegram_linked_at", None),
        recovery_codes_remaining=len(codes),
        last_login_at=getattr(u, "last_login_at", None),
        last_login_ip=getattr(u, "last_login_ip", None),
    )


@dataclass
class AdminMfaService:
    async def overview(
        self, current_user: User, db: AsyncSession,
    ) -> MfaOverviewResponse:
        _require_admin(current_user)
        result = await db.execute(
            select(User).where(User.is_active == True)  # noqa: E712
            .order_by(User.email)
        )
        users = result.scalars().all()
        rows = [_row(u) for u in users]
        summary = MfaOverviewSummary(
            total=len(rows),
            mfa_enabled_count=sum(1 for r in rows if r.mfa_enabled),
            telegram_linked_count=sum(1 for r in rows if r.telegram_linked),
            no_2fa_count=sum(1 for r in rows if not r.mfa_enabled),
        )
        return MfaOverviewResponse(users=rows, summary=summary)

    async def force_disable_mfa(
        self,
        user_id: UUID,
        request: Request,
        current_user: User,
        db: AsyncSession,
    ) -> None:
        _require_owner(current_user)
        if str(user_id) == str(current_user.id):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Невозможно сбросить собственную 2FA через этот endpoint. "
                "Используйте /mfa/disable со своим recovery-кодом.",
            )
        result = await db.execute(select(User).where(User.id == user_id))
        target: Optional[User] = result.scalar_one_or_none()
        if target is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Пользователь не найден",
            )

        was_enabled = bool(getattr(target, "mfa_enabled", False))
        had_tg = bool(getattr(target, "telegram_chat_id_encrypted", None))
        from app.services.mfa_service import get_recovery_codes as _grc
        had_recovery = bool(_grc(target))

        target.mfa_enabled = False
        target.mfa_method = MfaMethod.NONE
        from app.services.mfa_service import set_recovery_codes
        set_recovery_codes(target, None)
        target.telegram_chat_id_encrypted = None
        target.telegram_username = None
        target.telegram_linked_at = None
        target.telegram_link_token_hashed = None
        target.telegram_link_token_expires_at = None

        try:
            await append_audit_entry(
                db,
                actor_id=str(current_user.id),
                actor_email=current_user.email,
                action="mfa.force_disabled_by_admin",
                entity_type="user",
                entity_id=str(target.id),
                notes=(
                    f"target={target.email} mfa_was={was_enabled} "
                    f"tg_was={had_tg} recovery_was={had_recovery}"
                ),
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent", "")[:512],
            )
        except Exception as e:
            log.error(
                "audit failed for mfa.force_disabled_by_admin: %s",
                e, exc_info=True,
            )

        await db.commit()
