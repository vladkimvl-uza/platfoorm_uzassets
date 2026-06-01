"""Data access for Telegram bot callbacks."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.encryption import decrypt
from app.models.company import Company
from app.models.moderation import ModerationSubmission
from app.models.project import Project
from app.models.task import Task
from app.models.user import Role, User


class BotCallbacksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── chat_id → User ───────────────────────────────────────────

    async def find_user_by_chat_id(self, chat_id: int) -> Optional[User]:
        """Brute scan linked users — decrypt and match.
        OK because never more than a few hundred linked users."""
        result = await self.session.execute(
            select(User)
            .where(User.telegram_chat_id_encrypted.is_not(None))
            .options(selectinload(User.roles).selectinload(Role.permissions))
        )
        for u in result.scalars().all():
            try:
                plain = decrypt(u.telegram_chat_id_encrypted)
                if plain and int(plain) == int(chat_id):
                    return u
            except Exception:
                continue
        return None

    # ─── submission ───────────────────────────────────────────────

    async def get_submission(self, sub_id: UUID) -> Optional[ModerationSubmission]:
        return await self.session.get(ModerationSubmission, sub_id)

    # ─── tg-link token lookup ─────────────────────────────────────

    async def find_user_by_link_token_hash(self, token_hash: str) -> Optional[User]:
        res = await self.session.execute(
            select(User).where(User.telegram_link_token_hashed == token_hash)
        )
        return res.scalar_one_or_none()

    # ─── task / project ───────────────────────────────────────────

    async def get_task(self, task_id) -> Optional[Task]:
        res = await self.session.execute(
            select(Task).where(Task.id == task_id)
        )
        return res.scalar_one_or_none()

    async def get_project(self, project_id) -> Optional[Project]:
        res = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return res.scalar_one_or_none()

    async def get_company(self, company_id) -> Optional[Company]:
        return await self.session.get(Company, company_id)

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def flush(self) -> None:
        await self.session.flush()
