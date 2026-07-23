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
from datetime import UTC, datetime
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
from app.models.system_config import SystemConfig
from app.models.user import User
from app.schemas.ai import (
    AiConfigIn,
    AiConfigOut,
    AiHealthOut,
    ChatRequest,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ExecBriefRequest,
)
from app.services.ai_context import build_ai_context
from app.services.ai_exec_brief import build_exec_brief_context
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
    # Глобальный тумблер выключает ассистента для ОРГАНИЗАЦИИ; владелец (он же им
    # управляет) доступа не теряет — иначе режим owner_only при выкл. тумблере
    # запирал бы и самого владельца.
    if not await _assistant_active(db) and not getattr(user, "is_owner", False):
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
            system=system, prompt=prompt, model="ai-deep", max_tokens=6000, temperature=None,
            tools=[WEB_SEARCH_TOOL], timeout=190.0,
        )
    except Exception as e_web:  # noqa: BLE001
        # web-поиск мог быть недоступен/медленным — фолбэк без него по истории.
        logger.warning("AI forecast web call failed, fallback no-web: %s", e_web)
        try:
            text = await complete_once(
                system=system, prompt=prompt, model="ai-deep", max_tokens=4000, temperature=None,
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


# ─────────────── Сохранённые результаты ИИ (прогноз / HLF-анализ) ───────────────
# Портфельный артефакт, ОБЩИЙ для всех: один сгенерировал → все видят последний
# результат до новой генерации. Хранится в system_config под ключом
# ai_saved:<kind>:<scope> (scope = роль/вкладка для hlf, 'default' для прогноза).
_SAVED_KINDS = {"forecast", "hlf", "kpi"}


@router.get("/saved/{kind}")
async def list_saved_ai_outputs(
    kind: str,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """Все сохранённые результаты вида kind (для hlf — по всем ролям/scope)."""
    if kind not in _SAVED_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown kind")
    prefix = f"ai_saved:{kind}:"
    rows = (await db.execute(
        select(SystemConfig).where(SystemConfig.key.like(prefix + "%"))
    )).scalars().all()
    return {"saved": {r.key[len(prefix):]: r.value for r in rows}}


@router.put("/saved/{kind}/{scope}")
async def save_ai_output(
    kind: str,
    scope: str,
    payload: dict,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """Сохранить/перезаписать результат генерации (общий для всех, до новой генерации)."""
    if kind not in _SAVED_KINDS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown kind")
    scope = re.sub(r"[^A-Za-z0-9_.-]", "", scope)[:64] or "default"
    body = payload.get("payload")
    if not isinstance(body, dict):
        body = payload
    value = {
        **body,
        "_generated_by": str(user.id),
        "_generated_at": datetime.now(UTC).isoformat(),
    }
    key = f"ai_saved:{kind}:{scope}"
    existing = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    )).scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db.add(SystemConfig(
            key=key, value=value, description=f"AI saved {kind}/{scope}",
        ))
    await db.commit()
    return {"ok": True, "scope": scope, "generated_at": value["_generated_at"]}


# ─── ИИ-анализ высокоуровневых показателей (кросс-компанийный) ─────
@router.post("/hlf-analysis")
async def ai_hlf_analysis(
    payload: dict,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """Полный кросс-компанийный анализ высокоуровневых показателей портфеля.

    Фронт присылает посчитанную матрицу KPI по всем компаниям; ИИ (deep-тир +
    web) разбирает КАЖДЫЙ показатель: лидеры/аутсайдеры, выбросы, отраслевые
    бенчмарки, риски и сквозные выводы для инвесткомитета."""
    if not is_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI is not configured")
    if not await _assistant_active(db) and not getattr(user, "is_owner", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ИИ-ассистент деактивирован владельцем")
    year = payload.get("year")
    labels: dict = payload.get("metric_labels") or {}
    units: dict = payload.get("metric_units") or {}
    rows = payload.get("rows") or []
    if not rows or not labels:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нет данных для анализа")

    def _fmt(v, unit: str) -> str:
        if v is None:
            return "—"
        try:
            x = float(v)
        except (TypeError, ValueError):
            return "—"
        if unit == "%":
            return f"{x:+.1f}%"
        if unit == "x":
            return f"{x:.2f}x"
        return f"{x:,.0f}".replace(",", " ")

    lines = []
    for key, label in labels.items():
        unit = units.get(key, "")
        cells = [
            f"{(r.get('name') or r.get('code'))} {_fmt((r.get('kpis') or {}).get(key), unit)}"
            for r in rows
        ]
        lines.append(f"### {label}\n" + "; ".join(cells))
    matrix_text = "\n".join(lines)

    scenario = str(payload.get("scenario") or "cfo").lower()
    focus = str(payload.get("focus") or "").strip()
    if focus:
        _common = (
            f"Тебе даны высокоуровневые финансовые показатели ОДНОЙ компании — «{focus}» — "
            f"за {year} год. Используй web_search для актуальных отраслевых бенчмарков, цен на "
            "сырьё и макро Узбекистана. Дай ГЛУБОКИЙ разбор ИМЕННО ЭТОЙ компании: по каждому "
            "показателю — значение, сравнение с отраслевым бенчмарком (лучше/хуже и насколько), "
            "интерпретация; затем сквозные связки (маржа↔леверидж, ликвидность, долг, качество "
            "прибыли FCF vs Net margin, эффективность капитала ROE/ROA), сильные/слабые стороны, "
            "риски. ФОРМАТ: строгий деловой Markdown — заголовки, списки, при уместности таблицы. "
            "БЕЗ эмодзи. Числа с единицами. По-русски. Не выдумывай цифры — опирайся на данные."
        )
    else:
        _common = (
            f"Тебе дана матрица высокоуровневых финансовых показателей по ВСЕМ компаниям "
            f"портфеля за {year} год. Используй web_search для актуальных отраслевых "
            "бенчмарков, цен на сырьё и макро Узбекистана. ФОРМАТ: строгий деловой Markdown "
            "— заголовки, маркированные списки, при уместности компактные таблицы. БЕЗ "
            "эмодзи. Числа с единицами. По-русски. Не выдумывай цифры — опирайся на матрицу."
        )
    _persona = {
        "cfo": (
            "Ты — senior CFO и член инвесткомитета. Цель — операционно-финансовое "
            "здоровье портфеля и что чинить.\n"
            "ПО КАЖДОМУ ПОКАЗАТЕЛЮ: лидеры/аутсайдеры (с числами), медиана и разброс, "
            "выбросы, отраслевой бенчмарк, интерпретация.\n"
            "СКВОЗНОЕ: связки маржа-леверидж, риски ликвидности (Current ratio) и долга "
            "(Debt/EBITDA), качество прибыли (FCF vs Net margin), эффективность капитала "
            "(ROE/ROA), качество раскрытия. Заверши ПЛАНОМ ДЕЙСТВИЙ CFO: где резать "
            "издержки, где рефинансировать долг, где высвобождать оборотный капитал."
        ),
        "investor": (
            "Ты — институциональный инвестор/портфельный управляющий с мандатом разместить "
            "капитал. Главная цель — КУДА НАПРАВИТЬ ДЕНЬГИ при наличии инвестиций.\n"
            "ПО КАЖДОМУ ПОКАЗАТЕЛЮ: кратко — кто силён/слаб против бенчмарка.\n"
            "ГЛАВНОЕ — ИНВЕСТ-ТЕЗИС: ранжируй компании по привлекательности вложений "
            "(risk-adjusted) — кто недооценён/с потенциалом роста, кто структурно слаб. "
            "Дай явные рекомендации по АЛЛОКАЦИИ КАПИТАЛА: какие компании/секторы "
            "наращивать, какие сокращать/избегать, какие развивать (capex/M&A); куда "
            "направить свободный кэш — реинвест в высокий ROE vs гашение долга vs "
            "дивиденды. Сформулируй 3-5 конкретных инвест-идей с обоснованием (драйверы, "
            "риски, горизонт). Учитывай мировые цены на продукцию секторов и макро."
        ),
        "shareholder": (
            "Ты — крупный акционер (взгляд собственника). Цель — создание акционерной "
            "стоимости и возврат капитала.\n"
            "ПО КАЖДОМУ ПОКАЗАТЕЛЮ: кратко — вклад в стоимость против бенчмарка.\n"
            "ГЛАВНОЕ: устойчивость и потенциал ДИВИДЕНДОВ (FCF, леверидж, payout), "
            "доходность на капитал (ROE/ROA) против стоимости капитала, кто создаёт/"
            "разрушает стоимость, качество корпуправления и раскрытия. Дай рекомендации "
            "собственнику: где требовать рост дивидендов/байбек, где реинвестировать ради "
            "роста стоимости, где менять стратегию/менеджмент, какие риски для капитала."
        ),
    }
    system = _persona.get(scenario, _persona["cfo"]) + "\n" + _common
    if focus:
        prompt = f"Компания: {focus}. Год: {year}. Показатели компании:\n\n{matrix_text}"
    else:
        prompt = (
            f"Год: {year}. Компаний в выборке: {len(rows)}. "
            f"Матрица показателей (значение на компанию):\n\n{matrix_text}"
        )
    try:
        text = await complete_once(
            system=system, prompt=prompt, model="ai-deep", max_tokens=8000,
            temperature=None, tools=[WEB_SEARCH_TOOL], timeout=200.0,
        )
    except Exception as e_web:  # noqa: BLE001
        logger.warning("HLF analysis web call failed, fallback no-web: %s", e_web)
        try:
            text = await complete_once(
                system=system, prompt=prompt, model="ai-deep", max_tokens=6000,
                temperature=None, timeout=100.0,
            )
        except Exception as e2:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI analysis failed: {e2}")
    return {"analysis": (text or "").strip()}


@router.post("/kpi-analysis")
async def ai_kpi_analysis(
    payload: dict,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """ИИ-анализ KPI: исполнение показателей, связь KPI↔финансы, прогноз будущих KPI.

    Фронт присылает KPI-матрицу (индикаторы: план/факт/выполнение/направление/вес +
    ключ связи bp_metric_key со строкой ОФР) и — опционально — финансовую матрицу
    (HLF) тех же компаний для связки KPI↔финансы. Режим mode: performance |
    correlation | forecast. Deep-тир + web-поиск, как /ai/hlf-analysis."""
    if not is_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI is not configured")
    if not await _assistant_active(db) and not getattr(user, "is_owner", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ИИ-ассистент деактивирован владельцем")
    year = payload.get("year")
    period = str(payload.get("period") or "year")
    mode = str(payload.get("mode") or "performance").lower()
    focus = str(payload.get("focus") or "").strip()
    kpi_rows = payload.get("kpi_rows") or []
    fin_rows = payload.get("fin_rows") or []
    fin_labels: dict = payload.get("fin_labels") or {}
    fin_units: dict = payload.get("fin_units") or {}
    if not kpi_rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нет KPI-данных для анализа")

    def _num(v, unit: str = "") -> str:
        if v is None:
            return "—"
        try:
            x = float(v)
        except (TypeError, ValueError):
            return str(v)
        if unit == "%":
            return f"{x:.0f}%"
        s = f"{x:,.1f}".rstrip("0").rstrip(".").replace(",", " ")
        return f"{s} {unit}".strip()

    # KPI-матрица текстом: компания → РУКОВОДИТЕЛЬ (менеджер) → индикаторы.
    # По каждому индикатору — годовой план/факт/ожидаемое + КВАРТАЛЬНЫЙ разрез,
    # вес, направление, связь со строкой ОФР. Даём ИИ ВСЕ показатели и ВСЕХ
    # руководителей — ничего не агрегируем и не отбрасываем.
    kpi_blocks: list[str] = []
    for r in kpi_rows:
        nm = r.get("name") or r.get("code") or "—"
        block = [f"## {nm}"]
        managers = r.get("managers")
        if managers is None and r.get("indicators"):  # обратная совместимость (плоский формат)
            managers = [{"title": "—", "role": None, "indicators": r.get("indicators")}]
        for mgr in (managers or []):
            mrole = mgr.get("role")
            block.append(f"### Руководитель: {mgr.get('title') or '—'}" + (f" ({mrole})" if mrole else ""))
            for ind in (mgr.get("indicators") or []):
                unit = ind.get("unit") or ""
                dr = "↓меньше=лучше" if str(ind.get("dir")) == "down" else "↑больше=лучше"
                w = ind.get("weight")
                w_s = f", вес {w}" if w not in (None, "") else ""
                bp = ind.get("bp_key")
                link = f" [строка ОФР: {bp}]" if bp else ""
                pct = ind.get("pct")
                pct_s = f", выполнение {float(pct):.0f}%" if pct is not None else ""
                parts = [f"план {_num(ind.get('plan'), unit)}", f"факт {_num(ind.get('fact'), unit)}"]
                if ind.get("expect") is not None:
                    parts.append(f"ожидаемое {_num(ind.get('expect'), unit)}")
                qparts = []
                for q in ("q1", "q2", "q3", "q4"):
                    qc = (ind.get("quarters") or {}).get(q)
                    if qc:
                        qparts.append(f"{q.upper()} п{_num(qc.get('plan'), unit)}/ф{_num(qc.get('fact'), unit)}")
                qline = ("; кварталы: " + ", ".join(qparts)) if qparts else ""
                block.append(
                    f"- {ind.get('name') or '—'}: " + ", ".join(parts) + f"{pct_s} ({dr}{w_s}){link}{qline}"
                )
        kpi_blocks.append("\n".join(block))
    kpi_text = "\n\n".join(kpi_blocks)

    # Финансовый контекст (HLF-матрица тех же компаний), если прислан
    fin_text = ""
    if fin_rows and fin_labels:
        fblocks = []
        for key, label in fin_labels.items():
            u = fin_units.get(key, "")
            vals = "; ".join(
                f"{fr.get('name') or fr.get('code')} {_num((fr.get('kpis') or {}).get(key), u)}"
                for fr in fin_rows
            )
            fblocks.append(f"- {label}: {vals}")
        fin_text = (
            "\n\nФИНАНСОВЫЙ КОНТЕКСТ (высокоуровневые фин-показатели тех же компаний — "
            "для связки KPI↔финансы):\n" + "\n".join(fblocks)
        )

    # Модельный прогноз (детерминированный движок core/forecast) — ОПОРА для
    # forecast-режима: числа воспроизводимы, ИИ их интерпретирует/корректирует,
    # а не выдумывает. Фронт присылает результат GET /kpi/{co}/forecast.
    def _fc_ind_seg(ind: dict) -> str:
        u = ind.get("unit") or ""
        qf = ind.get("quarterly") or {}
        af = ind.get("annual") or {}
        seg = [f"- {ind.get('name') or '—'}"]
        if qf.get("expected_year") is not None:
            seg.append(f"ожид. итог года {_num(qf.get('expected_year'), u)} [{qf.get('method')}/{qf.get('confidence')}]")
        qproj = qf.get("projections") or []
        if qproj:
            seg.append("остаток кв.: " + ", ".join(
                f"{str(p.get('period')).upper()} {_num(p.get('value'), u)}" for p in qproj))
        aproj = af.get("projections") or []
        if aproj:
            parts = []
            for p in aproj:
                base = f"{p.get('period')} {_num(p.get('value'), u)} [{_num(p.get('low'), u)}…{_num(p.get('high'), u)}]"
                qs = p.get("quarters")
                if qs:
                    base += " (кв.: " + ", ".join(
                        f"Q{i + 1} {_num(qs[i], u)}" for i in range(min(4, len(qs)))) + ")"
                parts.append(base)
            seg.append("будущие годы: " + ", ".join(parts) + f" [{af.get('method')}/{af.get('confidence')}]")
        return "; ".join(seg)

    def _fmt_forecast(fc: dict) -> str:
        if not fc:
            return ""
        # Портфельная форма: {portfolio: [{name, completion, indicators:[...]}]}
        if fc.get("portfolio"):
            plines: list[str] = []
            for co in fc["portfolio"]:
                comp = co.get("completion") or {}
                head = f"• {co.get('name') or '—'}"
                if comp.get("projections"):
                    head += " — прогноз выполнения: " + ", ".join(
                        f"{p.get('period')}: {_num(p.get('value'), '%')}" for p in comp["projections"]
                    ) + f" [{comp.get('confidence')}]"
                plines.append(head)
                for ind in (co.get("indicators") or [])[:6]:
                    plines.append("  " + _fc_ind_seg(ind))
            if not plines:
                return ""
            return (
                "\n\nМОДЕЛЬНЫЙ ПРОГНОЗ ПО ПОРТФЕЛЮ (детерминированный движок — ОПОРА; "
                "числа воспроизводимы, коридор [low…high]):\n" + "\n".join(plines)
            )
        lines: list[str] = []
        comp = fc.get("completion") or {}
        if comp.get("projections"):
            cp = ", ".join(f"{p.get('period')}: {_num(p.get('value'), '%')}" for p in comp["projections"])
            lines.append(f"Сводное выполнение компании (тренд, надёжность {comp.get('confidence')}): {cp}")
        for mgr in fc.get("managers") or []:
            for ind in mgr.get("indicators") or []:
                lines.append(_fc_ind_seg(ind))
        if not lines:
            return ""
        return (
            "\n\nМОДЕЛЬНЫЙ ПРОГНОЗ (детерминированный движок — ОПОРА; числа воспроизводимы. "
            "Квартальный = план × темп (pace); годовой = OLS/CAGR-тренд с коридором [low…high]. "
            "method: pace/seasonal/run_rate/plan | ols/cagr | none=нет данных):\n" + "\n".join(lines)
        )

    forecast_text = _fmt_forecast(payload.get("forecast") or {}) if mode == "forecast" else ""

    _common_fmt = (
        "Используй web_search для отраслевых бенчмарков, цен на продукцию секторов и макро "
        "Узбекистана. ФОРМАТ: строгий деловой Markdown с заголовками-секциями. Числовые "
        "сравнения, разбор показателей и ПРОГНОЗЫ оформляй ТАБЛИЦАМИ (Markdown |стб|стб|) — "
        "это обязательно для читаемости и выгрузки в Excel. БЕЗ эмодзи. Числа с единицами. "
        "По-русски. Не выдумывай — опирайся на данные. ОБЯЗАТЕЛЬНО учитывай НАПРАВЛЕНИЕ "
        "(↑больше=лучше / ↓меньше=лучше) и ВЕС показателя, а также РУКОВОДИТЕЛЯ, отвечающего "
        "за показатель (структура сгруппирована по руководителям)."
    )
    _persona = {
        "performance": (
            "Ты — директор по стратегии и эффективности. Разбери ИСПОЛНЕНИЕ KPI компаний:\n"
            "- кто на цели / в риске / провалил (с числами план-факт-выполнение), с учётом веса "
            "и направления;\n"
            "- ключевые провалы (высокий вес × большой разрыв) и достижения;\n"
            "- связь операционных KPI с финансовым результатом (по пометкам [фин.метрика ОФР] и "
            "финансовому контексту): где операционные метрики отражаются в выручке/марже/прибыли.\n"
            "Заверши ПЛАНОМ: что чинить в первую очередь и почему."
        ),
        "correlation": (
            "Ты — аналитик данных / контроллер. Найди ВЗАИМОСВЯЗИ между операционными KPI и "
            "финансовыми показателями компаний:\n"
            "- какие KPI ДРАЙВЯТ финансовый результат (выручку, маржу, EBITDA, прибыль, ROE) — "
            "формулируй гипотезы и подтверждай цифрами из данных;\n"
            "- где операционные KPI ОПЕРЕЖАЮТ или ОТСТАЮТ от финансовых (лид/лаг-индикаторы);\n"
            "- отдели корреляцию от причинности; отметь неочевидные связки между компаниями/"
            "секторами. Опирайся на пометки [фин.метрика ОФР:key] (прямая связь KPI↔строка ОФР) "
            "и финансовый контекст. Дай карту «KPI → финансовый эффект»."
        ),
        "forecast": (
            "Ты — стратег-прогнозист. Спрогнозируй БУДУЩИЕ KPI компаний (кварталы и годы).\n"
            "ВАЖНО: тебе дан блок «МОДЕЛЬНЫЙ ПРОГНОЗ» — детерминированные проекции движка "
            "(pace по кварталам, OLS/CAGR-тренд по годам, с коридором надёжности). Это твоя "
            "ОПОРА: бери его числа как базовый сценарий, НЕ переизобретай их. Твоя задача — "
            "интерпретировать, при необходимости КОРРЕКТИРОВАТЬ с учётом отраслевых/макро-факторов "
            "(web) и ЯВНО объяснять расхождения с моделью. Где method=none (нет истории) — "
            "обоснуй прогноз качественно и пометь низкую надёжность.\n"
            "1) ПРОГНОЗ СУЩЕСТВУЮЩИХ KPI ПО ГОДАМ — ОБЯЗАТЕЛЬНО ТАБЛИЦЕЙ со столбцами: "
            "Показатель | Руководитель | Тек. факт | Прогноз (базовый) | Пессим. | Оптим. | "
            "Надёжность | Драйверы и риски. Базовый/пессим./оптим. соотноси с коридором "
            "[low…high] модели, по каждому будущему году.\n"
            "2) ПРОГНОЗ ПО КВАРТАЛАМ — ОБЯЗАТЕЛЬНО ТАБЛИЦЕЙ: Показатель | Год | Q1 | Q2 | Q3 | Q4 | "
            "Итог года. Для остатка ТЕКУЩЕГО года бери квартальные проекции модели; для БУДУЩИХ "
            "лет — квартальную разбивку модели (в блоке model помечена «кв.: Q1..Q4», это сезонность "
            "показателя), при необходимости скорректируй сезонность и поясни.\n"
            "3) НОВЫЕ KPI — ОБЯЗАТЕЛЬНО ТАБЛИЦЕЙ: Новый KPI | Определение | Ед. | Направление | "
            "Целевое (след. год) | Q1 | Q2 | Q3 | Q4 | Драйвер / связь с финрезультатом. Предложи "
            "3-5 показателей, которых сейчас НЕТ, под специфику сектора/компании. У новых KPI НЕТ "
            "истории — цель и квартальную разбивку обоснуй от драйверов (объём, цена, смежные "
            "метрики, отраслевые практики из web) и ЯВНО пометь надёжность как низкую (экспертная).\n"
            "Кратко прокомментируй ключевые прогнозы и расхождения с моделью под таблицами."
        ),
    }
    system = _persona.get(mode, _persona["performance"]) + "\n" + _common_fmt
    scope_line = f"Компания: {focus}. " if focus else f"Компаний в выборке: {len(kpi_rows)}. "
    prompt = (
        f"{scope_line}Год: {year}, период: {period}.\n\n"
        "KPI по компаниям, СГРУППИРОВАНЫ ПО РУКОВОДИТЕЛЯМ; по каждому показателю — "
        "годовой план/факт/ожидаемое + квартальный разрез, выполнение, направление, "
        "вес, связь со строкой ОФР:\n\n"
        f"{kpi_text}{fin_text}{forecast_text}"
    )
    try:
        text = await complete_once(
            system=system, prompt=prompt, model="ai-deep", max_tokens=8000,
            temperature=None, tools=[WEB_SEARCH_TOOL], timeout=200.0,
        )
    except Exception as e_web:  # noqa: BLE001
        logger.warning("KPI analysis web call failed, fallback no-web: %s", e_web)
        try:
            text = await complete_once(
                system=system, prompt=prompt, model="ai-deep", max_tokens=6000,
                temperature=None, timeout=100.0,
            )
        except Exception as e2:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI analysis failed: {e2}")
    return {"analysis": (text or "").strip()}


EXEC_BRIEF_INSTRUCTIONS = (
    "Тебе дан срез ИСПОЛНЕНИЯ портфеля по секторам за год. КЛЮЧЕВОЕ: проект СОСТОИТ из "
    "задач, и прогресс проекта = доля выполненных задач. Поэтому реальные причины "
    "задержек ищи НА УРОВНЕ ЗАДАЧ — в их статусах, сроках и КОММЕНТАРИЯХ (то, что люди "
    "заполняют в карточках задач и проектов). По проблемным проектам тебе даны конкретные "
    "открытые задачи и комментарии к ним — опирайся именно на них.\n"
    "Дай КРАТКУЮ деловую сводку для Совета директоров:\n"
    "1) Текущее состояние и КЛЮЧЕВЫЕ ПРИЧИНЫ задержек — называй КОНКРЕТНЫЕ задачи, которые "
    "тормозят проект, и опирайся на их комментарии/ход. Не выдумывай — если причины в "
    "данных нет, так и скажи.\n"
    "2) Логические ВЗАИМОСВЯЗИ: как застрявшие задачи/проекты одних секторов влияют на "
    "другие, общие паттерны (просрочки, нехватка ресурсов, согласования).\n"
    "3) Конкретные СОВЕТЫ/действия (что, по какой задаче и кому делать).\n"
    "ФОРМАТ: строгий деловой Markdown, по-русски, БЕЗ эмодзи. Где уместно — компактные GFM-таблицы "
    "(топ блокирующих задач, секторы по прогрессу). 1-2 ключевых графика блоком "
    "```uzachart {валидный Chart.js config json}```. Кратко и по делу — без воды."
)


@router.post("/exec-sector-brief")
async def exec_sector_brief(
    payload: ExecBriefRequest,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """ИИ-сводка исполнения задач/проектов по секторам (виджет ожиданий акционера).

    Собирает проекты/прогресс/просрочку + комментарии по проблемным на сервере
    (RBAC-scope), затем Opus даёт краткую сводку: причины, взаимосвязи, советы."""
    if not is_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI is not configured")
    if not getattr(user, "is_owner", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ИИ-аналитик исполнения доступен только владельцу")
    if not await _assistant_active(db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ИИ-ассистент деактивирован владельцем")
    try:
        context, scope = await build_exec_brief_context(
            db, user, year=payload.year, sectors=payload.sectors, company_id=payload.company_id,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("exec-brief context build failed")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Сбор данных не удался: {e}")

    focus_hint = {
        "risks": "ОСОБЫЙ ФОКУС: риски и проблемные проекты.",
        "delays": "ОСОБЫЙ ФОКУС: причины задержек.",
    }.get((payload.focus or "").lower(), "")
    system = await build_ai_context(db, role="analyst", style="structured")
    system += "\n\n" + EXEC_BRIEF_INSTRUCTIONS + (("\n" + focus_hint) if focus_hint else "")
    prompt = f"Данные исполнения по секторам:\n\n{context}"
    try:
        text = await complete_once(
            system=system, prompt=prompt, model=payload.model or "ai-deep",
            max_tokens=6000, temperature=None, timeout=190.0,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI brief failed: {e}")

    saved = {
        "analysis": (text or "").strip(),
        "scope": scope,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    key = f"ai_saved:exec_brief:{payload.year}:{payload.focus or 'overview'}"
    row = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    if row:
        row.value = saved
    else:
        db.add(SystemConfig(key=key, value=saved))
    await db.commit()
    return saved


@router.get("/exec-sector-brief/saved")
async def exec_sector_brief_saved(
    year: int,
    focus: str | None = None,
    user: User = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """Последняя сохранённая ИИ-сводка исполнения по секторам (owner-only)."""
    if not getattr(user, "is_owner", False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно только владельцу")
    key = f"ai_saved:exec_brief:{year}:{focus or 'overview'}"
    row = (await db.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    return row.value if (row and row.value) else {}


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
            detail="ИИ-движок не настроен",
        )
    # Владелец не теряет доступ при выключенном глобальном тумблере (см. /forecast).
    if not await _assistant_active(db) and not getattr(user, "is_owner", False):
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
