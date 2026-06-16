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
import re
from datetime import UTC
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import has_effective_permission, require_permission
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
    complete_once,
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

# ─── Режим доступа к ассистенту ───────────────────────────────────
# "owner_only" — только владелец (дефолт сейчас); "rbac" — по праву ai.view.
_ACCESS_KEY = "ai_access_mode"


async def _access_mode(db: AsyncSession) -> str:
    row = (await db.execute(select(AIConfig).where(AIConfig.key == _ACCESS_KEY))).scalar_one_or_none()
    if row is None:
        return "owner_only"  # дефолт: доступ только у владельца
    return str((row.value or {}).get("mode", "owner_only"))


async def _has_ai_access(user: User, db: AsyncSession) -> bool:
    """Есть ли у пользователя доступ к ассистенту с учётом режима."""
    if getattr(user, "is_owner", False):
        return True
    mode = await _access_mode(db)
    if mode == "owner_only":
        return False
    return await has_effective_permission(db, user, "ai.view")


async def require_ai_access(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Гейт пользовательских AI-эндпоинтов: режим owner_only / rbac."""
    if not await _has_ai_access(user, db):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Нет доступа к ИИ-ассистенту",
        )
    return user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["ai"])

# Нативный server-side web-поиск движка (включается флагом ChatRequest.web).
# Выполняется на стороне провайдера — отдельный API-ключ/инфраструктура не нужны.
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}


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
        "access_mode": await _access_mode(db),
        "has_access": await _has_ai_access(user, db),
    }


@router.put("/access-mode")
async def set_ai_access_mode(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Режим доступа к ассистенту — только владелец."""
    if not getattr(user, "is_owner", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Только владелец может менять доступ к ассистенту")
    mode = str((payload or {}).get("mode", ""))
    if mode not in ("owner_only", "rbac"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "mode должен быть 'owner_only' или 'rbac'")
    row = (await db.execute(select(AIConfig).where(AIConfig.key == _ACCESS_KEY))).scalar_one_or_none()
    if row is None:
        db.add(AIConfig(key=_ACCESS_KEY, value={"mode": mode}))
    else:
        row.value = {"mode": mode}
    await db.commit()
    return {"access_mode": mode}


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


# ─── ИИ-прогноз (структурный, для авто-заполнения таблиц) ─────────
@router.post("/forecast")
async def ai_forecast(
    payload: dict,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """ИИ генерирует прогноз показателя и возвращает {code: {year: value}}.
    Используется кнопкой «Прогноз ИИ» для авто-заполнения прогнозных колонок."""
    if not is_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI is not configured")
    if not await _assistant_active(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ИИ-ассистент деактивирован владельцем")
    metric = str((payload or {}).get("metric_label") or "показатель")
    try:
        target_years = [int(y) for y in (payload.get("target_years") or [])][:5]
    except (TypeError, ValueError):
        target_years = []
    series = payload.get("series") or []
    if not target_years or not series:
        return {"forecast": {}}
    lines = []
    for s in series[:30]:
        hist = ", ".join(
            f"{y}={v}" for y, v in (s.get("history") or {}).items() if v not in (None, 0)
        )
        if hist:
            lines.append(f'{s.get("code")}: {hist}')
    if not lines:
        return {"forecast": {}}
    system = (
        "Ты — CFO и корпоративный стратег с доступом к web-поиску. Тебе дан финансовый "
        "показатель и история по компаниям; построй ОБОСНОВАННЫЙ прогноз уровня "
        "инвесткомитета.\n"
        "МЕТОДОЛОГИЯ (применяй по сути показателя):\n"
        "• Выручка — драйверы спроса/цен/объёмов, доля рынка, отраслевой рост; для "
        "сырьевых компаний — мировые цены на их продукцию (нефть Brent/Urals, газ, медь, "
        "золото, уран, удобрения и т.д.) и курс сума.\n"
        "• Себестоимость — как доля выручки + цены на сырьё/энергию/труд; эффект масштаба.\n"
        "• Валовая/операционная прибыль, EBITDA, чистая прибыль — через МАРЖУ: тренд "
        "маржи + структурные сдвиги; держи логику «выручка → затраты → прибыль», не "
        "отрывай прибыль от динамики выручки.\n"
        "• Активы — рост с масштабом бизнеса, capex и оборотным капиталом; не быстрее "
        "выручки без причины.\n"
        "• Капитал — прошлый капитал + нераспределённая прибыль (реинвестирование) − "
        "дивиденды.\n"
        "• Обязательства/Долг — финансовая политика и leverage; график погашения/"
        "привлечения, процентные ставки.\n"
        "• Денежные средства — из денежного потока (операционный CF − capex − дивиденды "
        "± финансирование).\n"
        "ПРИНЦИПЫ: реалистичный базовый сценарий; учитывай замедление при насыщении и "
        "возврат к среднему; разовые всплески/провалы НЕ экстраполируй линейно; "
        "учитывай инфляцию, ВВП и бюджет Узбекистана, курс UZS, геополитику и санкционный "
        "фон. Для актуальных цен и макро ОБЯЗАТЕЛЬНО используй web_search.\n"
        "ФОРМАТ: сначала кратко обоснуй (драйверы, какие цены/курсы/макро и допущения "
        "учёл по этому показателю), ЗАТЕМ в КОНЦЕ верни блок ```json``` с объектом "
        "{\"<code>\":{\"<year>\":<число в млрд UZS>}} для ВСЕХ перечисленных кодов и лет."
    )
    prompt = (
        f"Спрогнозируй «{metric}» на годы {target_years} для компаний ниже по их "
        f"историческому ряду (значения в млрд UZS). Коды компаний возвращай ТОЧНО как "
        f"даны.\nИстория:\n" + "\n".join(lines)
    )
    text = ""
    try:
        text = await complete_once(
            system=system, prompt=prompt, max_tokens=6000, temperature=0.2,
            tools=[WEB_SEARCH_TOOL], timeout=190.0,
        )
    except Exception as e_web:  # noqa: BLE001
        # web-поиск мог быть недоступен/медленным — фолбэк без него по истории.
        logger.warning("AI forecast web call failed, fallback no-web: %s", e_web)
        try:
            text = await complete_once(
                system=system, prompt=prompt, max_tokens=4000, temperature=0.2,
                timeout=90.0,
            )
        except Exception as e2:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI forecast failed: {e2}")
    data: dict = {}
    block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = block.group(1) if block else None
    if candidate is None:
        obj = re.search(r"\{.*\}", text, re.S)
        candidate = obj.group(0) if obj else None
    if candidate:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            data = {}
    # Обоснование = текст ответа без JSON-блока (что ИИ учёл: цены, макро, геополитика).
    rationale = text
    if block:
        rationale = text.replace(block.group(0), "")
    elif candidate:
        rationale = text.replace(candidate, "")
    rationale = rationale.strip()[:4000]
    return {"forecast": data, "rationale": rationale}


# ─── Conversations CRUD ──────────────────────────────────────────

@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationCreate,
    service: AiAdminServiceDep,
    user: User = Depends(require_ai_access),
) -> ConversationOut:
    return await service.create_conversation(user.id, payload)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    service: AiAdminServiceDep,
    user: User = Depends(require_ai_access),
) -> list[ConversationOut]:
    return await service.list_conversations(user.id)


@router.get("/conversations/{conv_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conv_id: UUID,
    service: AiAdminServiceDep,
    user: User = Depends(require_ai_access),
) -> ConversationDetailOut:
    return await service.get_conversation(conv_id, user_id=user.id)


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: UUID,
    service: AiAdminServiceDep,
    user: User = Depends(require_ai_access),
) -> dict:
    return await service.delete_conversation(conv_id, user_id=user.id)


@router.patch("/conversations/{conv_id}", response_model=ConversationOut)
async def rename_conversation(
    conv_id: UUID,
    payload: ConversationCreate,
    service: AiAdminServiceDep,
    user: User = Depends(require_ai_access),
) -> ConversationOut:
    return await service.rename_conversation(
        conv_id, user_id=user.id, payload=payload,
    )


# ─── Streaming chat with tools ────────────────────────────────────

@router.post("/chat")
async def chat(
    payload: ChatRequest,
    service: AiAdminServiceDep,
    request: Request,
    user: User = Depends(require_ai_access),
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

    # Текст запроса пользователя (для rich-аудита ai.query ниже).
    _q = (payload.messages[-1].content or "").strip()

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

    # Rich-аудит запроса к ИИ (с текстом запроса). /ai/chat исключён из generic
    # middleware (SKIP_PREFIXES), поэтому пишем здесь явно — видно «кто·что спросил».
    try:
        from app.services.audit_service import write_event
        await write_event(
            db,
            actor_id=user.id,
            actor_email=getattr(user, "email", None),
            action="AI_QUERY",
            module="ai",
            entity_type="ai_query",
            entity_label="ИИ-ассистент" + (" · web" if payload.web else ""),
            notes=("Запрос: " + _q)[:1000],
            http_method="POST",
            http_path="/ai/chat",
            http_status=200,
            ip_address=(request.client.host if request.client else None),
        )
        await db.commit()
    except Exception as _ae:
        logger.warning("ai audit write failed: %s", _ae)

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
    system_prompt += (
        "\n\n[ЭКСПОРТ] Если пользователь просит Excel/Word/выгрузку/«сформировать в xlsx» — "
        "просто выведи данные обычной markdown-таблицей. Под твоим ответом у пользователя "
        "есть кнопка «Excel» для скачивания таблицы. НЕ придумывай кнопки/ссылки для "
        "скачивания и НЕ обещай форматы, которые ты не выводишь таблицей в ответе."
    )
    if payload.web:
        system_prompt += (
            "\n\n[ДОСТУПЕН WEB-ПОИСК] У тебя есть инструмент web_search. "
            "Для ЛЮБЫХ актуальных и рыночных данных — цены на нефть (Brent/Urals), "
            "газ, металлы, золото; курсы валют; биржевые котировки; ставки ЦБ; "
            "новости, IPO, макропоказатели — ОБЯЗАТЕЛЬНО вызывай web_search и бери "
            "свежие цифры из результатов. НИКОГДА не отвечай по памяти на такие "
            "вопросы: твои внутренние знания устарели. В ответе указывай значение, "
            "дату актуальности и источник."
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

        chat_tools = list(TOOLS) + ([WEB_SEARCH_TOOL] if payload.web else [])
        try:
            async for raw in stream_chat_with_tools(
                system=system_prompt, messages=api_messages,
                tools=chat_tools, db=db, tool_dispatcher=execute_tool,
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
