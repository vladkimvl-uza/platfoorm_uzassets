"""Data access for API Keys + Service Accounts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.audit import AuditLog
from app.models.user import Permission, User


class ApiKeysRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── catalog counts ───────────────────────────────────────────

    async def count_total_keys(self) -> int:
        res = await self.session.execute(select(func.count(ApiKey.id)))
        return int(res.scalar_one() or 0)

    async def count_active_keys(self) -> int:
        res = await self.session.execute(
            select(func.count(ApiKey.id)).where(and_(
                ApiKey.revoked_at.is_(None),
                or_(ApiKey.expires_at.is_(None),
                    ApiKey.expires_at > datetime.now(timezone.utc)),
            ))
        )
        return int(res.scalar_one() or 0)

    async def count_service_accounts(self) -> int:
        res = await self.session.execute(
            select(func.count(User.id)).where(User.is_service_account.is_(True))
        )
        return int(res.scalar_one() or 0)

    # ─── service accounts ─────────────────────────────────────────

    async def list_service_accounts(self, *, q: Optional[str]):
        base = select(User).where(User.is_service_account.is_(True))
        if q:
            like = f"%{q}%"
            base = base.where(or_(
                User.email.ilike(like), User.full_name.ilike(like),
            ))
        rows = (await self.session.execute(
            base.order_by(User.created_at.desc())
        )).scalars().all()
        return list(rows)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        res = await self.session.execute(
            select(User).where(User.email == email)
        )
        return res.scalars().first()

    async def get_service_account(self, sa_id: UUID) -> Optional[User]:
        sa = await self.session.get(User, sa_id)
        return sa if sa and sa.is_service_account else None

    async def list_active_keys_for_sa(self, sa_id: UUID):
        res = await self.session.execute(
            select(ApiKey).where(and_(
                ApiKey.service_account_id == sa_id,
                ApiKey.revoked_at.is_(None),
            ))
        )
        return list(res.scalars().all())

    # ─── api keys ─────────────────────────────────────────────────

    async def list_keys(
        self,
        *,
        service_account_id: Optional[UUID],
        include_revoked: bool,
    ):
        base = select(ApiKey)
        if service_account_id is not None:
            base = base.where(ApiKey.service_account_id == service_account_id)
        if not include_revoked:
            base = base.where(ApiKey.revoked_at.is_(None))
        rows = (await self.session.execute(
            base.order_by(ApiKey.created_at.desc())
        )).scalars().all()
        return list(rows)

    async def get_key(self, key_id: UUID) -> Optional[ApiKey]:
        return await self.session.get(ApiKey, key_id)

    # ─── permission validation ────────────────────────────────────

    async def existing_permission_codes(self, codes: Sequence[str]) -> set[str]:
        if not codes:
            return set()
        res = await self.session.execute(
            select(Permission.code).where(Permission.code.in_(codes))
        )
        return set(res.scalars().all())

    # ─── audit log ────────────────────────────────────────────────

    async def list_key_audit(self, key_id: UUID, *, limit: int):
        rows = (await self.session.execute(
            select(AuditLog).where(AuditLog.api_key_id == key_id)
            .order_by(AuditLog.created_at.desc()).limit(limit)
        )).scalars().all()
        return list(rows)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
