"""Data access for AI module — conversations, messages, user config."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ai_conversation import AiConversation, AiMessage
from app.models.ai_user_config import AiUserConfig


class AiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ─── user config ──────────────────────────────────────────────

    async def get_config(self, user_id: UUID) -> Optional[AiUserConfig]:
        res = await self.session.execute(
            select(AiUserConfig).where(AiUserConfig.user_id == user_id)
        )
        return res.scalar_one_or_none()

    # ─── conversations ────────────────────────────────────────────

    async def get_conversation(
        self, conv_id: UUID, *, user_id: UUID,
    ) -> Optional[AiConversation]:
        res = await self.session.execute(
            select(AiConversation).where(
                AiConversation.id == conv_id,
                AiConversation.user_id == user_id,
            )
        )
        return res.scalar_one_or_none()

    async def get_conversation_with_messages(
        self, conv_id: UUID, *, user_id: UUID,
    ) -> Optional[AiConversation]:
        res = await self.session.execute(
            select(AiConversation)
            .where(
                AiConversation.id == conv_id,
                AiConversation.user_id == user_id,
            )
            .options(selectinload(AiConversation.messages))
        )
        return res.scalar_one_or_none()

    async def list_recent_conversations(
        self, user_id: UUID, *, limit: int = 100,
    ) -> list[AiConversation]:
        res = await self.session.execute(
            select(AiConversation)
            .where(AiConversation.user_id == user_id)
            .order_by(desc(AiConversation.updated_at))
            .limit(limit)
        )
        return list(res.scalars().all())

    async def count_messages(self, conv_id: UUID) -> int:
        res = await self.session.execute(
            select(func.count(AiMessage.id))
            .where(AiMessage.conversation_id == conv_id)
        )
        return int(res.scalar_one() or 0)

    async def last_message_preview(self, conv_id: UUID) -> Optional[str]:
        res = await self.session.execute(
            select(AiMessage.content)
            .where(AiMessage.conversation_id == conv_id)
            .order_by(desc(AiMessage.created_at))
            .limit(1)
        )
        return res.scalar_one_or_none()

    # ─── mutations ────────────────────────────────────────────────

    def add(self, obj) -> None:
        self.session.add(obj)

    async def delete(self, obj) -> None:
        await self.session.delete(obj)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, obj) -> None:
        await self.session.refresh(obj)
