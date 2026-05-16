"""
AI Assistant API endpoints — Pack 7.5.

Adds tool_use to chat: minimal system prompt + tool definitions
let Claude pull specific data on demand instead of stuffing everything
into context.
"""
from __future__ import annotations
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.ai_conversation import AiConversation, AiMessage
from app.models.ai_user_config import AiUserConfig
from app.models.user import User
from app.schemas.ai import (
    AiConfigIn,
    AiConfigOut,
    AiHealthOut,
    ChatRequest,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    MessageOut,
    VALID_ROLES,
    VALID_STYLES,
)
from app.services.ai_context import build_ai_context
from app.services.ai_service import (
    DEFAULT_MODEL,
    extract_text_and_stats,
    is_enabled,
    stream_chat_with_tools,
)
from app.services.ai_tools import TOOLS, execute_tool


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


def require_admin(user: "User" = Depends(get_current_user)) -> "User":
    """Owner или role `admin` — единая логика из app.core.security.is_super_admin."""
    from app.core.security import is_super_admin
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/health", response_model=AiHealthOut)
async def ai_health(_user: User = Depends(require_admin)) -> AiHealthOut:
    return AiHealthOut(
        enabled=is_enabled(),
        model=DEFAULT_MODEL,
        has_api_key=is_enabled(),
    )


# ─────────────────── Pack 7.2: User config ───────────────────

async def _get_or_create_config(db: AsyncSession, user_id: UUID) -> AiUserConfig:
    res = await db.execute(
        select(AiUserConfig).where(AiUserConfig.user_id == user_id)
    )
    cfg = res.scalar_one_or_none()
    if cfg is None:
        cfg = AiUserConfig(user_id=user_id)
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg


@router.get("/config", response_model=AiConfigOut)
async def get_ai_config(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiConfigOut:
    cfg = await _get_or_create_config(db, user.id)
    return AiConfigOut(
        role=cfg.role, style=cfg.style,
        temperature=cfg.temperature, max_tokens=cfg.max_tokens,
        custom_instructions=cfg.custom_instructions,
    )


@router.put("/config", response_model=AiConfigOut)
async def update_ai_config(
    payload: AiConfigIn,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AiConfigOut:
    if payload.role and payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role: {payload.role}")
    if payload.style and payload.style not in VALID_STYLES:
        raise HTTPException(status_code=400, detail=f"Invalid style: {payload.style}")

    cfg = await _get_or_create_config(db, user.id)
    if payload.role is not None: cfg.role = payload.role
    if payload.style is not None: cfg.style = payload.style
    if payload.temperature is not None: cfg.temperature = payload.temperature
    if payload.max_tokens is not None: cfg.max_tokens = payload.max_tokens
    if payload.custom_instructions is not None: cfg.custom_instructions = payload.custom_instructions

    await db.commit()
    await db.refresh(cfg)
    return AiConfigOut(
        role=cfg.role, style=cfg.style,
        temperature=cfg.temperature, max_tokens=cfg.max_tokens,
        custom_instructions=cfg.custom_instructions,
    )


# ─────────────────── Conversations CRUD (unchanged from 7.2) ───────────────────

@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conv = AiConversation(user_id=user.id, title=payload.title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return ConversationOut(
        id=conv.id, title=conv.title,
        created_at=conv.created_at, updated_at=conv.updated_at,
        message_count=0,
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    res = await db.execute(
        select(AiConversation)
        .where(AiConversation.user_id == user.id)
        .order_by(desc(AiConversation.updated_at))
        .limit(100)
    )
    convs = list(res.scalars().all())
    if not convs:
        return []
    out: list[ConversationOut] = []
    for c in convs:
        cnt_res = await db.execute(
            select(func.count(AiMessage.id)).where(AiMessage.conversation_id == c.id)
        )
        last_res = await db.execute(
            select(AiMessage.content)
            .where(AiMessage.conversation_id == c.id)
            .order_by(desc(AiMessage.created_at))
            .limit(1)
        )
        out.append(
            ConversationOut(
                id=c.id, title=c.title,
                created_at=c.created_at, updated_at=c.updated_at,
                message_count=int(cnt_res.scalar_one() or 0),
                last_message_preview=(last_res.scalar_one_or_none() or "")[:120],
            )
        )
    return out


@router.get("/conversations/{conv_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conv_id: UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConversationDetailOut:
    res = await db.execute(
        select(AiConversation)
        .where(AiConversation.id == conv_id, AiConversation.user_id == user.id)
        .options(selectinload(AiConversation.messages))
    )
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
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


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    res = await db.execute(
        select(AiConversation).where(
            AiConversation.id == conv_id, AiConversation.user_id == user.id
        )
    )
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
    await db.commit()
    return {"deleted": True, "id": str(conv_id)}


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
async def rename_conversation(
    conv_id: UUID,
    payload: ConversationCreate,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    res = await db.execute(
        select(AiConversation).where(
            AiConversation.id == conv_id, AiConversation.user_id == user.id
        )
    )
    conv = res.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if payload.title is not None:
        conv.title = payload.title
    await db.commit()
    await db.refresh(conv)
    cnt_res = await db.execute(
        select(func.count(AiMessage.id)).where(AiMessage.conversation_id == conv.id)
    )
    return ConversationOut(
        id=conv.id, title=conv.title,
        created_at=conv.created_at, updated_at=conv.updated_at,
        message_count=int(cnt_res.scalar_one() or 0),
    )


# ─────────────────── Streaming chat (Pack 7.5: with tools) ───────────────────

@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not is_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI is not configured (ANTHROPIC_API_KEY missing)",
        )
    if not payload.messages or payload.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="Last message must be from 'user'")

    # Resolve / create conversation
    conv: AiConversation | None = None
    if payload.conversation_id:
        res = await db.execute(
            select(AiConversation).where(
                AiConversation.id == payload.conversation_id,
                AiConversation.user_id == user.id,
            )
        )
        conv = res.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        first_user = next(
            (m.content for m in payload.messages if m.role == "user"), ""
        )
        title = (first_user or "Новый разговор")[:80]
        conv = AiConversation(user_id=user.id, title=title)
        db.add(conv)
        await db.flush()

    # Persist incoming user message
    user_msg = AiMessage(
        conversation_id=conv.id,
        role="user",
        content=payload.messages[-1].content,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(conv)

    # Apply user config + payload overrides
    saved_cfg = await _get_or_create_config(db, user.id)
    eff_role = payload.role or saved_cfg.role
    eff_style = payload.style or saved_cfg.style
    eff_temp = payload.temperature if payload.temperature is not None else saved_cfg.temperature
    eff_max = payload.max_tokens or saved_cfg.max_tokens
    eff_custom = saved_cfg.custom_instructions or ""

    system_prompt = await build_ai_context(
        db,
        role=eff_role,
        style=eff_style,
        custom_instructions=eff_custom,
    )

    api_messages = [
        {"role": m.role, "content": m.content}
        for m in payload.messages
        if m.content and m.role in ("user", "assistant")
    ]

    captured_events: list[dict] = []
    captured_tool_calls: list[dict] = []
    conv_id_str = str(conv.id)

    async def event_generator():
        meta = {"type": "meta", "conversation_id": conv_id_str}
        yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n".encode("utf-8")

        try:
            async for raw in stream_chat_with_tools(
                system=system_prompt,
                messages=api_messages,
                tools=TOOLS,
                db=db,
                tool_dispatcher=execute_tool,
                max_tokens=eff_max,
                temperature=eff_temp,
            ):
                yield raw
                # Parse for capture
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
                        elif evt_name in ("message", "data") and isinstance(obj, dict):
                            if obj.get("type"):
                                captured_events.append(obj)
                except Exception:
                    pass
        except Exception as e:
            logger.exception("AI stream failed")
            err = {"type": "error", "error": {"message": str(e)}}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")

        full_text, tin, tout, stop = extract_text_and_stats(captured_events)
        if full_text or captured_tool_calls:
            try:
                _factory = _resolve_async_session_factory()
                async with _factory() as session2:
                    # Persist assistant message with tool-calls metadata in stop_reason
                    am = AiMessage(
                        conversation_id=conv.id,
                        role="assistant",
                        content=full_text,
                        tokens_in=tin,
                        tokens_out=tout,
                        stop_reason=stop or ("tool_use" if captured_tool_calls else None),
                    )
                    session2.add(am)
                    res = await session2.execute(
                        select(AiConversation).where(AiConversation.id == conv.id)
                    )
                    c = res.scalar_one_or_none()
                    if c:
                        from datetime import datetime, timezone as _tz
                        c.updated_at = datetime.now(_tz.utc)
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
