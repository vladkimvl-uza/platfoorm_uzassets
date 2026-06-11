"""AI Assistant API — thin HTTP layer (refactored 2026-05-25).

Core services NOT touched:
- `app/services/ai_service.py` — stream_chat_with_tools, extract_text_and_stats, is_enabled
- `app/services/ai_context.py` — build_ai_context (system prompt builder)
- `app/services/ai_tools.py` — TOOLS catalog + execute_tool

Streaming chat endpoint stays in route file (SSE generator with
mid-stream event capture for persistence is transport-specific).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import require_permission
from app.dependencies.ai import AiAdminServiceDep
from app.models.ai import AIConfig
from app.models.ai_conversation import AiConversation, AiMessage
from app.models.user import User
from app.schemas.ai import (
    AiConfigIn,
    AiConfigOut,
    AiHealthOut,
    ChatRequest,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
)
from app.services.ai_context import build_ai_context
from app.services.ai_service import (
    DEFAULT_MODEL,
    extract_text_and_stats,
    is_enabled,
    stream_chat_with_tools,
)
from app.services.ai_tools import TOOLS, execute_tool, set_current_user_id


def _resolve_async_session_factory():
    import importlib
    for path, attr in [
        ("app.core.database", "async_session_factory"),
        ("app.core.database", "AsyncSessionLocal"),
        ("app.core.database", "async_session"),
        ("app.database", "async_session_factory"),
        ("app.database", "AsyncSessionLocal"),
        ("app.db.session", "async_session_factory"),
    ]:
        try:
            mod = importlib.import_module(path)
            f = getattr(mod, attr, None)
            if f is not None:
                return f
        except ImportError:
            continue
    raise RuntimeError("Cannot resolve async session factory")


def require_admin(user: User = Depends(get_current_user)) -> User:
    from app.core.security import is_super_admin
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Доступ к пользовательскому ИИ (чат + беседы) — по праву ai.view, которое
# admin/OWNER выдают через сетку RBAC «Доступ к модулям». super-admin (owner/
# admin-роль) проходит автоматически (bypass внутри require_permission).
# Настройки модели и health остаются строго админскими (require_admin).
_require_ai = require_permission("ai.view")


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


# ─── Health ───────────────────────────────────────────────────────

@router.get("/health", response_model=AiHealthOut)
async def ai_health(_user: User = Depends(require_admin)) -> AiHealthOut:
    return AiHealthOut(
        enabled=is_enabled(),
        model=DEFAULT_MODEL,
        has_api_key=is_enabled(),
    )


# ─── User config ──────────────────────────────────────────────────

@router.get("/config", response_model=AiConfigOut)
async def get_ai_config(
    service: AiAdminServiceDep,
    user: User = Depends(require_admin),
) -> AiConfigOut:
    return await service.get_config(user.id)


@router.put("/config", response_model=AiConfigOut)
async def update_ai_config(
    payload: AiConfigIn,
    service: AiAdminServiceDep,
    user: User = Depends(require_admin),
) -> AiConfigOut:
    return await service.update_config(user.id, payload)


# ─── Глобальная активация ассистента (owner toggle) ───────────────

_ACT_KEY = "assistant_active"


async def _assistant_active(db: AsyncSession) -> bool:
    """Глобальный флаг включён/выключен (по умолчанию — включён)."""
    row = (await db.execute(select(AIConfig).where(AIConfig.key == _ACT_KEY))).scalar_one_or_none()
    if row is None:
        return True
    return bool((row.value or {}).get("active", True))


@router.get("/activation")
async def get_ai_activation(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {
        "active": await _assistant_active(db),
        "can_toggle": bool(getattr(user, "is_owner", False)),
    }


@router.put("/activation")
async def set_ai_activation(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not getattr(user, "is_owner", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только владелец может управлять ассистентом")
    active = bool(payload.get("active", True))
    row = (await db.execute(select(AIConfig).where(AIConfig.key == _ACT_KEY))).scalar_one_or_none()
    if row is None:
        db.add(AIConfig(key=_ACT_KEY, value={"active": active}))
    else:
        row.value = {"active": active}
    await db.commit()
    return {"active": active, "can_toggle": True}


# ─── Conversations CRUD ──────────────────────────────────────────

@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationCreate,
    service: AiAdminServiceDep,
    user: User = Depends(_require_ai),
) -> ConversationOut:
    return await service.create_conversation(user.id, payload)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    service: AiAdminServiceDep,
    user: User = Depends(_require_ai),
) -> list[ConversationOut]:
    return await service.list_conversations(user.id)


@router.get("/conversations/{conv_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conv_id: UUID,
    service: AiAdminServiceDep,
    user: User = Depends(_require_ai),
) -> ConversationDetailOut:
    return await service.get_conversation(conv_id, user_id=user.id)


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: UUID,
    service: AiAdminServiceDep,
    user: User = Depends(_require_ai),
) -> dict:
    return await service.delete_conversation(conv_id, user_id=user.id)


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
async def rename_conversation(
    conv_id: UUID,
    payload: ConversationCreate,
    service: AiAdminServiceDep,
    user: User = Depends(_require_ai),
) -> ConversationOut:
    return await service.rename_conversation(
        conv_id, user_id=user.id, payload=payload,
    )


# ─── Streaming chat with tools ────────────────────────────────────

@router.post("/chat")
async def chat(
    payload: ChatRequest,
    service: AiAdminServiceDep,
    user: User = Depends(_require_ai),
    db: AsyncSession = Depends(get_db),
):
    """Streaming SSE chat with AI engine tool_use."""
    if not is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI is not configured (ANTHROPIC_API_KEY missing)",
        )
    if not await _assistant_active(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ИИ-ассистент деактивирован владельцем",
        )
    # Атрибуция action-инструментов (notify_user) — кто отправитель
    set_current_user_id(user.id)
    if not payload.messages or payload.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="Last message must be from 'user'")

    first_user_content = next(
        (m.content for m in payload.messages if m.role == "user"), "",
    )
    conv = await service.resolve_chat_conversation(
        user_id=user.id,
        conversation_id=payload.conversation_id,
        first_user_content=first_user_content,
    )

    # Persist incoming user message (commit before stream)
    user_msg = AiMessage(
        conversation_id=conv.id, role="user",
        content=payload.messages[-1].content,
    )
    db.add(user_msg)
    await db.commit()

    saved_cfg = await service.get_effective_config(user.id)
    eff_role = payload.role or saved_cfg.role
    eff_style = payload.style or saved_cfg.style
    eff_model = payload.model or saved_cfg.model
    eff_temp = payload.temperature if payload.temperature is not None else saved_cfg.temperature
    eff_max = payload.max_tokens or saved_cfg.max_tokens
    eff_custom = saved_cfg.custom_instructions or ""

    system_prompt = await build_ai_context(
        db, role=eff_role, style=eff_style, custom_instructions=eff_custom,
    )

    api_messages = [
        {"role": m.role, "content": m.content}
        for m in payload.messages
        if m.content and m.role in ("user", "assistant")
    ]

    captured_events: list[dict] = []
    captured_tool_calls: list[dict] = []
    conv_id_str = str(conv.id)
    conv_id = conv.id

    async def event_generator():
        meta = {"type": "meta", "conversation_id": conv_id_str}
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n".encode()

        try:
            async for raw in stream_chat_with_tools(
                system=system_prompt, messages=api_messages,
                tools=TOOLS, db=db, tool_dispatcher=execute_tool,
                model=eff_model, max_tokens=eff_max, temperature=eff_temp,
            ):
                yield raw
                try:
                    text = raw.decode("utf-8", errors="ignore")
                    for line_block in text.split("\n\n"):
                        evt_name = "message"
                        data_str = ""
                        for ln in line_block.split("\n"):
                            if ln.startswith("event:"):
                                evt_name = ln[6:].strip()
                            elif ln.startswith("data:"):
                                data_str += ln[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            obj = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        if evt_name == "tool_use_start":
                            captured_tool_calls.append({
                                "name": obj.get("name"),
                                "args": obj.get("args"),
                                "id": obj.get("id"),
                            })
                        elif evt_name == "tool_use_end":
                            pass
                        elif isinstance(obj, dict) and obj.get("type"):
                            captured_events.append(obj)
                except Exception:
                    pass
        except Exception as e:
            logger.exception("AI stream failed")
            err = {"type": "error", "error": {"message": str(e)}}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode()

        full_text, tin, tout, stop = extract_text_and_stats(captured_events)
        if full_text or captured_tool_calls:
            try:
                _factory = _resolve_async_session_factory()
                async with _factory() as session2:
                    am = AiMessage(
                        conversation_id=conv_id, role="assistant",
                        content=full_text,
                        tokens_in=tin, tokens_out=tout,
                        stop_reason=stop or ("tool_use" if captured_tool_calls else None),
                    )
                    session2.add(am)
                    res = await session2.execute(
                        select(AiConversation).where(AiConversation.id == conv_id)
                    )
                    c = res.scalar_one_or_none()
                    if c:
                        from datetime import datetime
                        c.updated_at = datetime.now(UTC)
                    await session2.commit()
            except Exception:
                logger.exception("Failed to persist assistant message")

        yield b"event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
