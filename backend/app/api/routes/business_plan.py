"""Business Plan API — thin HTTP layer (refactored 2026-05-25).

bp_compute / bp_attention_issues / sector_*/kpi_attention_issues live in
the existing core `app/services/bp_kpi_helpers.py` — those are tightly-
coupled formulas reused across BP, KPI, dashboard. Service delegates.

Moderation gate for `bulk_upsert` stays in route (post-commit
side-effect that needs the request actor).
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.editor_lock import check_editor_token, compute_bp_editor_token
from app.core.access import (
    allowed_company_ids,
    ensure_company_access,
    has_unrestricted_view,
)
from app.core.security import has_effective_permission
from app.dependencies.bp import BpForecastServiceDep, BpServiceDep
from app.models.bp_kpi import BP_METRICS
from app.models.user import User
from app.schemas.bp_forecast import BpCompanyForecast, BpQuarterOutlook
from app.schemas.bp_kpi import (
    BpAttentionIssue,
    BpAvailableCompany,
    BpBulkUpsert,
    BpCommentRead,
    BpCommentUpsert,
    BpComputed,
    BpRecordUpsert,
    BpSummary,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/bp", tags=["business-plan"])

_BP_LABELS = {m["key"]: m["label"] for m in BP_METRICS}


def _bp_metric_label(code: str) -> str:
    return _BP_LABELS.get(code, code)


def _fmt_money(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(v)


async def _scope(db: AsyncSession, user: User) -> Optional[list[UUID]]:
    if has_unrestricted_view(user):
        return None
    res = await allowed_company_ids(db, user)
    return list(res) if res is not None else []


# ─── Metadata ─────────────────────────────────────────────────────

@router.get("/metrics")
async def list_metrics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    return BP_METRICS


# ─── Available companies + years ──────────────────────────────────

@router.get("/available-companies", response_model=list[BpAvailableCompany])
async def available_companies(
    service: BpServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    try:
        return await service.available_companies(scope_company_ids=await _scope(db, user))
    except Exception:
        log.exception("BP available-companies failed")
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить список компаний бизнес-плана. Попробуйте позже.",
        )


# ─── Portfolio summary ────────────────────────────────────────────

@router.get("/summary/{year}/{period}", response_model=BpSummary)
async def get_summary(
    year: int,
    period: str,
    service: BpServiceDep,
    metric: str = "revenue",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Portfolio BP summary. `metric` chooses headline aggregation."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    try:
        return await service.get_summary(
            year, period,
            headline_metric=metric,
            scope_company_ids=await _scope(db, user),
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("BP summary %s/%s failed", year, period)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить сводку бизнес-плана. Попробуйте позже.",
        )


# ─── Raw records (editor) ────────────────────────────────────────
# IMPORTANT: registered BEFORE /{company_id}/{year}/{period}

@router.get("/raw/{company_id}/{year}")
async def get_raw_records(
    company_id: UUID,
    year: int,
    service: BpServiceDep,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch raw business-plan records (P&L + SOFP rows) for company × year.

    Used by the BP editor. Computed/derived rows live at GET /{company}/{year}/{period}."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    # Optimistic-lock: токен состояния (company, year) — редактор вернёт его в
    # If-Match при сохранении; расхождение → 409 (кто-то сохранил параллельно).
    response.headers["X-Editor-Token"] = await compute_bp_editor_token(
        db, company_id=company_id, year=year)
    return await service.get_raw_records(company_id, year)


# ─── Прогноз БП (детерминированный движок; ПЕРЕД catch-all) ───────

@router.get("/forecast/{company_id}/{base_year}", response_model=BpCompanyForecast)
async def forecast_company(
    company_id: UUID,
    base_year: int,
    service: BpForecastServiceDep,
    horizon: int = 2,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Прогноз финансовых метрик БП на будущие годы + кварталы (сезонность).

    Детерминированный движок core/forecast по годовому ряду факта/ожидаемого.
    Числа воспроизводимы; ИИ-слой (/ai/bp-analysis mode=forecast) берёт их опорой.
    Путь с literal `forecast` — чтобы не коллидировать с /{company_id}/{year}/{period}."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    return await service.forecast_company(company_id, base_year, horizon)


@router.get("/quarter-forecast/{year}", response_model=BpQuarterOutlook)
async def quarter_forecast(
    year: int,
    service: BpForecastServiceDep,
    metric: str = "revenue",
    company_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Прогноз оставшихся кварталов года (компания или сводно по портфелю).

    Движок forecast_quarters на ДЕЛЬТАХ «за квартал» (кварталы БП хранятся
    нарастающим итогом); сезонный fallback — прошлогодние кварталы. Питает
    ghost-бары в «Динамике по кварталам». Путь 2-сегментный — с catch-all
    /{company_id}/{year}/{period} не коллидирует."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    try:
        if company_id is not None:
            await ensure_company_access(db, user, company_id)
            return await service.quarter_outlook(year, metric, company_id=company_id)
        return await service.quarter_outlook(
            year, metric, scope_company_ids=await _scope(db, user),
        )
    except HTTPException:
        raise
    except Exception:
        log.exception("BP quarter-forecast %s/%s failed", year, metric)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось построить квартальный прогноз. Попробуйте позже.",
        )


# ─── Computed (catch-all) ────────────────────────────────────────

@router.get("/{company_id}/{year}/{period}", response_model=BpComputed)
async def get_computed(
    company_id: UUID,
    year: int,
    period: str,
    service: BpServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch BP with all derived metrics computed (margins, growth, FX-normalised).

    Period is one of: year, q1, q2, q3, q4. Used by BP dashboards and PDF reports."""
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    try:
        return await service.get_computed(company_id, year, period)
    except HTTPException:
        raise
    except Exception:
        log.exception("BP compute %s/%s/%s failed", company_id, year, period)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось рассчитать бизнес-план. Попробуйте позже.",
        )


# ─── Upserts ──────────────────────────────────────────────────────

@router.post("/upsert")
async def upsert_one(
    payload: BpRecordUpsert,
    service: BpServiceDep,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")
    await ensure_company_access(db, user, payload.company_id)
    await service.upsert_one(payload)
    # Деталь уведомления: «Выручка 2025: план 1 200, факт 1 100».
    _parts = []
    if payload.plan is not None:
        _parts.append(f"план {_fmt_money(payload.plan)}")
    if payload.fact is not None:
        _parts.append(f"факт {_fmt_money(payload.fact)}")
    request.state.activity_summary = (
        f"{_bp_metric_label(payload.metric)} {payload.year}: {', '.join(_parts) or 'обновлено'}"
    )
    request.state.activity_entity = "Бизнес-план"
    return {"ok": True}


@router.post("/bulk-upsert")
async def bulk_upsert(
    payload: BpBulkUpsert,
    service: BpServiceDep,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    if_match: Optional[str] = Header(None, alias="If-Match"),
):
    """Editor save: replace many cells in one transaction.

    Pack 148: gated by moderation (module='business_plan', action='bulk_upsert').
    """
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")

    # Scope-проверка ДО модерации по КАЖДОЙ компании в наборе: иначе
    # ограниченный пользователь мог отправить на модерацию (а после аппрува —
    # записать) данные бизнес-плана чужой компании вне своего доступа.
    for cid in {r.company_id for r in payload.records}:
        await ensure_company_access(db, user, cid)

    # Moderation gate (uses first record's company_id for rule matching)
    from app.services.moderation_service import gate_or_apply
    first = payload.records[0] if payload.records else None

    # Optimistic-lock: если редактор прислал If-Match — сверяем со свежим токеном
    # (company, year) первой записи ДО записи/модерации. Расхождение → 409.
    if first is not None:
        current_tok = await compute_bp_editor_token(
            db, company_id=first.company_id, year=first.year)
        check_editor_token(
            scope_name=f"bp/{first.company_id}/{first.year}",
            expected_token=if_match, current_token=current_tok)
    queued, sub = await gate_or_apply(
        db, user=user,
        module="business_plan", action="bulk_upsert",
        entity_id=str(first.company_id) if first else None,
        entity_label=f"BP {first.year}" if first else "BP",
        company_id=first.company_id if first else None,
        sector_id=None,
        year=first.year if first else None,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Bulk-upsert {len(payload.records)} ячеек бизнес-плана",
    )
    if queued:
        return {
            "queued": True, "submission_id": str(sub.id),
            "status": sub.status,
            "message": "Изменение отправлено на модерацию",
        }

    n = await service.bulk_upsert(payload, scope_company_ids=await _scope(db, user))
    if first:
        request.state.activity_summary = f"Обновлено {len(payload.records)} показателей за {first.year}"
        request.state.activity_entity = "Бизнес-план"
        # Перевыдаём токен — редактор продолжает работу без перезагрузки.
        response.headers["X-Editor-Token"] = await compute_bp_editor_token(
            db, company_id=first.company_id, year=first.year)
    return {"upserted": n}


@router.delete("/{company_id}/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_year(
    company_id: UUID,
    year: int,
    service: BpServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.delete"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.delete required")
    await ensure_company_access(db, user, company_id)
    await service.delete_year(company_id, year)


# ─── Attention issues ─────────────────────────────────────────────

@router.get("/attention/{company_id}/{year}/{period}", response_model=list[BpAttentionIssue])
async def get_attention(
    company_id: UUID,
    year: int,
    period: str,
    service: BpServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    return await service.attention(company_id, year, period)


# ─── Comments ─────────────────────────────────────────────────────

@router.get("/comment/{company_id}/{year}/{period}", response_model=Optional[BpCommentRead])
async def get_comment(
    company_id: UUID,
    year: int,
    period: str,
    service: BpServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.view required")
    await ensure_company_access(db, user, company_id)
    return await service.get_comment(company_id, year, period)


@router.put("/comment", response_model=BpCommentRead)
async def upsert_comment(
    payload: BpCommentUpsert,
    service: BpServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "bp.edit"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "bp.edit required")
    await ensure_company_access(db, user, payload.company_id)
    return await service.upsert_comment(payload, author_id=user.id)
