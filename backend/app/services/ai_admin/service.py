"""Use cases for AI module — config + conversations.

Naming `ai_admin/` to coexist with existing core services:
- `app/services/ai_service.py` (stream_chat_with_tools, extract_text_and_stats, is_enabled)
- `app/services/ai_context.py` (build_ai_context — system prompt builder)
- `app/services/ai_tools.py` (TOOLS, execute_tool — Claude tool catalog)

Those stay untouched.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.ai_conversation import AiConversation, AiMessage
from app.models.ai_user_config import AiUserConfig
from app.schemas.ai import (
    AiConfigIn, AiConfigOut, ConversationCreate, ConversationDetailOut,
    ConversationOut, MessageOut, VALID_MODELS, VALID_ROLES, VALID_STYLES,
)
from app.uow.ports import UnitOfWorkABC


def _config_to_out(cfg: AiUserConfig) -> AiConfigOut:
    return AiConfigOut(
        role=cfg.role, style=cfg.style, model=cfg.model,
        temperature=cfg.temperature, max_tokens=cfg.max_tokens,
        custom_instructions=cfg.custom_instructions,
    )


class AiAdminService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── config ───────────────────────────────────────────────────

    async def _ensure_config(self, user_id: UUID) -> AiUserConfig:
        cfg = await self.uow.ai.get_config(user_id)
        if cfg is None:
            cfg = AiUserConfig(user_id=user_id)
            self.uow.ai.add(cfg)
            await self.uow.ai.flush()
            await self.uow.ai.refresh(cfg)
        return cfg

    async def get_config(self, user_id: UUID) -> AiConfigOut:
        async with self.uow:
            cfg = await self._ensure_config(user_id)
            return _config_to_out(cfg)

    async def update_config(
        self, user_id: UUID, payload: AiConfigIn,
    ) -> AiConfigOut:
        if payload.role and payload.role not in VALID_ROLES:
            raise HTTPException(400, f"Invalid role: {payload.role}")
        if payload.style and payload.style not in VALID_STYLES:
            raise HTTPException(400, f"Invalid style: {payload.style}")
        if payload.model and payload.model not in VALID_MODELS:
            raise HTTPException(400, f"Invalid model: {payload.model}")

        async with self.uow:
            cfg = await self._ensure_config(user_id)
            if payload.role is not None:                 cfg.role = payload.role
            if payload.style is not None:                cfg.style = payload.style
            if payload.model is not None:                cfg.model = payload.model
            if payload.temperature is not None:          cfg.temperature = payload.temperature
            if payload.max_tokens is not None:           cfg.max_tokens = payload.max_tokens
            if payload.custom_instructions is not None:  cfg.custom_instructions = payload.custom_instructions
            await self.uow.ai.flush()
            await self.uow.ai.refresh(cfg)
            return _config_to_out(cfg)

    # ─── conversations CRUD ──────────────────────────────────────

    async def create_conversation(
        self, user_id: UUID, payload: ConversationCreate,
    ) -> ConversationOut:
        async with self.uow:
            conv = AiConversation(user_id=user_id, title=payload.title)
            self.uow.ai.add(conv)
            await self.uow.ai.flush()
            await self.uow.ai.refresh(conv)
            return ConversationOut(
                id=conv.id, title=conv.title,
                created_at=conv.created_at, updated_at=conv.updated_at,
                message_count=0,
            )

    async def list_conversations(self, user_id: UUID) -> list[ConversationOut]:
        async with self.uow:
            convs = await self.uow.ai.list_recent_conversations(user_id)
            out: list[ConversationOut] = []
            for c in convs:
                cnt = await self.uow.ai.count_messages(c.id)
                preview = await self.uow.ai.last_message_preview(c.id)
                out.append(ConversationOut(
                    id=c.id, title=c.title,
                    created_at=c.created_at, updated_at=c.updated_at,
                    message_count=cnt,
                    last_message_preview=(preview or "")[:120],
                ))
        return out

    async def get_conversation(
        self, conv_id: UUID, *, user_id: UUID,
    ) -> ConversationDetailOut:
        async with self.uow:
            conv = await self.uow.ai.get_conversation_with_messages(
                conv_id, user_id=user_id,
            )
            if not conv:
                raise HTTPException(404, "Conversation not found")
            return ConversationDetailOut(
                id=conv.id, title=conv.title,
                created_at=conv.created_at, updated_at=conv.updated_at,
                message_count=len(conv.messages),
                messages=[
                    MessageOut(
                        id=m.id, role=m.role, content=m.content,
                        created_at=m.created_at,
                        tokens_in=m.tokens_in, tokens_out=m.tokens_out,
                        stop_reason=m.stop_reason,
                    )
                    for m in conv.messages
                ],
            )

    async def delete_conversation(
        self, conv_id: UUID, *, user_id: UUID,
    ) -> dict:
        async with self.uow:
            conv = await self.uow.ai.get_conversation(conv_id, user_id=user_id)
            if not conv:
                raise HTTPException(404, "Conversation not found")
            await self.uow.ai.delete(conv)
            await self.uow.ai.flush()
        return {"deleted": True, "id": str(conv_id)}

    async def rename_conversation(
        self, conv_id: UUID, *, user_id: UUID, payload: ConversationCreate,
    ) -> ConversationOut:
        async with self.uow:
            conv = await self.uow.ai.get_conversation(conv_id, user_id=user_id)
            if not conv:
                raise HTTPException(404, "Conversation not found")
            if payload.title is not None:
                conv.title = payload.title
            await self.uow.ai.flush()
            await self.uow.ai.refresh(conv)
            cnt = await self.uow.ai.count_messages(conv.id)
            return ConversationOut(
                id=conv.id, title=conv.title,
                created_at=conv.created_at, updated_at=conv.updated_at,
                message_count=cnt,
            )

    # ─── chat helpers ─────────────────────────────────────────────

    async def resolve_chat_conversation(
        self,
        *,
        user_id: UUID,
        conversation_id: Optional[UUID],
        first_user_content: str,
    ) -> AiConversation:
        """Returns existing conversation (404 if foreign) or creates new one
        titled by first user message. Caller commits."""
        async with self.uow:
            if conversation_id:
                conv = await self.uow.ai.get_conversation(
                    conversation_id, user_id=user_id,
                )
                if not conv:
                    raise HTTPException(404, "Conversation not found")
                return conv
            title = (first_user_content or "Новый разговор")[:80]
            conv = AiConversation(user_id=user_id, title=title)
            self.uow.ai.add(conv)
            await self.uow.ai.flush()
            await self.uow.ai.refresh(conv)
            return conv

    async def get_effective_config(self, user_id: UUID) -> AiUserConfig:
        async with self.uow:
            return await self._ensure_config(user_id)
