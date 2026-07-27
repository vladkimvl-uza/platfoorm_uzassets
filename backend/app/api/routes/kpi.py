"""KPI dashboard REST API — thin HTTP layer.

Refactored 2026-05-25 (10-layer template pilot): этот файл больше не
содержит ни SQL queries, ни бизнес-логики. Каждый handler:
1. Проверяет permission (через `has_effective_permission` / `ensure_company_access`).
2. Делегирует в `KpiQueryService` или `KpiEditorService`.
3. Возвращает результат.

Все queries — в `app/repositories/kpi_repository.py`.
Вся логика — в `app/services/kpi/{query,editor}_service.py`.
Транзакции — `app/uow/impl.py`.

Endpoints (без изменений URL):
  GET    /kpi/available-companies
  GET    /kpi/{company_id}/{year}
  PUT    /kpi/{company_id}/{year}
  DELETE /kpi/{company_id}/{year}
  GET    /kpi/summary/{year}/{period}
  GET    /kpi/attention/{company_id}/{year}/{period}
  GET    /kpi/comment/{company_id}/{year}/{period}
  PUT    /kpi/comment
  GET    /kpi/templates
  POST   /kpi/load-template/{company_code}/{year}
  POST   /kpi/load-ngmk-template/{year}              (DEPRECATED)
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.access import allowed_company_ids, ensure_company_access, has_unrestricted_view
from app.core.security import has_effective_permission
from app.dependencies.kpi import (
    KpiEditorServiceDep,
    KpiForecastServiceDep,
    KpiQueryServiceDep,
)
from app.models.user import User
from app.schemas.bp_kpi import (
    BpAvailableCompany,
    KpiAttentionIssue,
    KpiCommentRead,
    KpiCommentUpsert,
    KpiCompanyYearUpsert,
    KpiManagerRead,
    KpiSummary,
)
from app.schemas.kpi_forecast import CompanyForecast, KpiPlanDraft

log = logging.getLogger(__name__)
router = APIRouter(prefix="/kpi", tags=["kpi"])


# ── permission helpers (keep thin) ────────────────────────────────

async def _require(db: AsyncSession, user: User, code: str) -> None:
    if not await has_effective_permission(db, user, code):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"{code} required")


# ─── Available companies + years ──────────────────────────────────

@router.get("/available-companies", response_model=list[BpAvailableCompany])
async def available_companies(
    service: KpiQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.view")
    scope = None if has_unrestricted_view(user) else (await allowed_company_ids(db, user) or [])
    return await service.list_available_companies(scope_company_ids=scope)


# ─── Full managers tree for one (company, year) ───────────────────

@router.get("/{company_id}/{year}", response_model=list[KpiManagerRead])
async def get_company_year(
    company_id: UUID,
    year: int,
    response: Response,
    service: KpiQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Fetch full KPI tree (managers → indicators) for a (company, year).

    Returns 403 if the caller lacks scope to this company. Issues an
    `X-Editor-Token` response header (optimistic lock) — must be echoed back as
    `If-Match` on the next PUT to avoid lost-update races."""
    await _require(db, user, "kpi.view")
    await ensure_company_access(db, user, company_id)
    # Optimistic-lock token — выдаётся client'у на GET, проверяется на PUT.
    from app.core.editor_lock import compute_kpi_editor_token
    response.headers["X-Editor-Token"] = await compute_kpi_editor_token(
        db, company_id=company_id, year=year,
    )
    return await service.get_company_year(company_id, year)


# ─── Replace tree (editor save) ───────────────────────────────────

@router.put("/{company_id}/{year}")
async def replace_company_year(
    company_id: UUID,
    year: int,
    payload: KpiCompanyYearUpsert,
    response: Response,
    request: Request,
    service: KpiEditorServiceDep,
    if_match: Optional[str] = Header(None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Replace ALL managers + indicators для (company, year).

    1) Permission + scope checks (HTTP-layer concern).
    2) Moderation gate — intercepts write если есть active rule.
    3) Optimistic-lock check.
    4) Atomic service.replace_year() — UoW гарантирует rollback при сбое.
    5) Post-commit side-effect — broadcast kpi_completion.
    """
    await _require(db, user, "kpi.edit")
    await ensure_company_access(db, user, company_id)

    # Optimistic-lock — отдельный contract (раздаём token на GET).
    from app.core.editor_lock import check_editor_token, compute_kpi_editor_token
    current_token = await compute_kpi_editor_token(db, company_id=company_id, year=year)
    check_editor_token(
        scope_name=f"kpi/{company_id}/{year}",
        expected_token=if_match,
        current_token=current_token,
    )

    # Moderation gate followup B2)
    from app.services.moderation_service import gate_or_apply
    queued, sub = await gate_or_apply(
        db, user=user,
        module="kpi", action="replace_year",
        entity_id=str(company_id),
        entity_label=f"KPI {year}",
        company_id=company_id, sector_id=None, year=year,
        payload=payload.model_dump(mode="json"),
        diff_summary=f"Замена дерева KPI на {len(payload.managers)} руководителей за {year}",
    )
    if queued:
        return {
            "queued": True,
            "submission_id": str(sub.id),
            "status": sub.status,
            "message": "Изменение отправлено на модерацию",
        }

    result = await service.replace_year(company_id, year, payload)
    request.state.activity_summary = f"Обновлено KPI за {year} · {len(payload.managers)} руководителей"
    request.state.activity_entity = "KPI"

    # Side-effect: WS broadcast kpi_completion. Best-effort, не блокирует ответ.
    await _broadcast_kpi_completion(db, company_id, year, user)

    # New editor token для chain-save без reload.
    response.headers["X-Editor-Token"] = await compute_kpi_editor_token(
        db, company_id=company_id, year=year,
    )
    return result


@router.delete("/{company_id}/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_year(
    company_id: UUID,
    year: int,
    service: KpiEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.delete")
    await ensure_company_access(db, user, company_id)
    await service.delete_year(company_id, year)


# ─── Прогноз KPI (детерминированный движок + грудинг ИИ) ──────────

@router.get("/plan-draft/{company_id}/{target_year}", response_model=KpiPlanDraft)
async def kpi_plan_draft(
    company_id: UUID,
    target_year: int,
    service: KpiForecastServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Черновик планов KPI на target_year из истории фактов (генератор
    «Рассчитать показатели»). Read-only: ничего не пишет — применение через
    редактор (только пустые планы) и штатный PUT replace_year (kpi.edit +
    модерация + optimistic-lock). Literal-путь — ПЕРЕД /{company_id}/{year}."""
    await _require(db, user, "kpi.view")
    await ensure_company_access(db, user, company_id)
    try:
        return await service.plan_draft(company_id, target_year)
    except HTTPException:
        raise
    except Exception:
        log.exception("KPI plan-draft %s/%s failed", company_id, target_year)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось построить черновик планов KPI. Попробуйте позже.",
        )


@router.get("/{company_id}/forecast/{base_year}", response_model=CompanyForecast)
async def forecast_company(
    company_id: UUID,
    base_year: int,
    service: KpiForecastServiceDep,
    horizon: int = 2,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Прогноз KPI компании: по кварталам текущего года + на будущие годы.

    Детерминированный движок (core/forecast): pace-adjusted план по кварталам,
    OLS/CAGR-тренд на годы, коридор надёжности. Числа воспроизводимы; ИИ-слой
    (/ai/kpi-analysis mode=forecast) получает их как опору. 3-сегментный путь —
    чтобы не коллидировать с `/{company_id}/{year}`."""
    await _require(db, user, "kpi.view")
    await ensure_company_access(db, user, company_id)
    return await service.forecast_company(company_id, base_year, horizon)


# ─── Portfolio summary ────────────────────────────────────────────

@router.get("/summary/{year}/{period}", response_model=KpiSummary)
async def get_summary(
    year: int,
    period: str,
    service: KpiQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.view")
    if period == "annual":
        period = "year"
    if period not in ("year", "q1", "q2", "q3", "q4"):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Invalid period: {period}")

    scope_set: Optional[set] = None
    if not has_unrestricted_view(user):
        scope = await allowed_company_ids(db, user)
        scope_set = set(scope or [])

    try:
        return await service.compute_summary(year, period, scope_company_ids=scope_set)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        log.error("kpi /summary/%s/%s failed: %s\n%s", year, period, e, traceback.format_exc())
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось вычислить сводку KPI. Попробуйте позже.",
        )


# ─── Attention ────────────────────────────────────────────────────

@router.get("/attention/{company_id}/{year}/{period}", response_model=list[KpiAttentionIssue])
async def get_attention(
    company_id: UUID,
    year: int,
    period: str,
    service: KpiQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.view")
    await ensure_company_access(db, user, company_id)
    return await service.get_attention(company_id, year, period)


# ─── Comments ─────────────────────────────────────────────────────

@router.get("/comment/{company_id}/{year}/{period}", response_model=Optional[KpiCommentRead])
async def get_comment(
    company_id: UUID,
    year: int,
    period: str,
    service: KpiQueryServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.view")
    await ensure_company_access(db, user, company_id)
    return await service.get_comment(company_id, year, period)


@router.put("/comment", response_model=KpiCommentRead)
async def upsert_comment(
    payload: KpiCommentUpsert,
    service: KpiEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.edit")
    await ensure_company_access(db, user, payload.company_id)
    return await service.upsert_comment(payload, author_id=user.id)


# ─── Templates ────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(
    service: KpiEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.view")
    return await service.list_templates()


@router.post("/load-template/{company_code}/{year}")
async def load_template(
    company_code: str,
    year: int,
    service: KpiEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(db, user, "kpi.import")
    # ensure_company_access проверяется внутри service после lookup-а co.id.
    # Здесь только базовая permission gate.
    co = None  # для lookup перед scope-check придётся читать DB:
    from sqlalchemy import func, select

    from app.models.company import Company
    res = await db.execute(select(Company).where(func.lower(Company.code) == company_code.lower()))
    co = res.scalar_one_or_none()
    if co is not None:
        await ensure_company_access(db, user, co.id)
    return await service.load_template(company_code, year)


@router.post("/load-ngmk-template/{year}", deprecated=True)
async def load_ngmk_template_compat(
    year: int,
    service: KpiEditorServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Deprecated alias for /load-template/ngmk/{year}."""
    return await load_template("ngmk", year, service, db, user)


# ─── Side-effect: broadcast kpi_completion (helper, не использует service)

async def _broadcast_kpi_completion(
    db: AsyncSession, company_id: UUID, year: int, user,
) -> None:
    """Push recomputed kpi_completion % to WS subscribers. Best-effort.

    Сохранён как helper здесь (не в service) потому что использует ту же
    session что и route — broadcasts происходят ПОСЛЕ commit основной
    транзакции, чтобы не показывать stale-данные.
    """
    try:
        from sqlalchemy import select

        from app.models.bp_kpi import KpiIndicator, KpiManager
        from app.services.bp_kpi_helpers import kpi_compute_completion
        from app.services.sync_broadcaster import broadcaster

        mgrs = list((await db.execute(
            select(KpiManager).where(KpiManager.company_id == company_id, KpiManager.year == year)
        )).scalars().all())
        if not mgrs:
            await broadcaster.broadcast_field_update(
                company_id=str(company_id), field_code="kpi_completion", value=None,
                source_module="kpi", actor_id=str(getattr(user, "id", "")) or None,
            )
            return
        mgr_ids = [m.id for m in mgrs]
        inds = list((await db.execute(
            select(KpiIndicator).where(KpiIndicator.manager_id.in_(mgr_ids))
        )).scalars().all())
        total_w = 0.0
        sum_wr = 0.0
        for ind in inds:
            try:
                w = float(ind.weight or 0)
            except (TypeError, ValueError):
                continue
            if w <= 0:
                continue
            # BAG-4 fix: считаем через единый хелпер — учитывает YTD-fallback
            # по кварталам и направление метрики (direction), как в summary.
            ratio = kpi_compute_completion(ind, "year")
            if ratio is None:
                continue
            total_w += w
            sum_wr += w * min(1.5, ratio)
        pct = round((sum_wr / total_w) * 100, 1) if total_w > 0 else None
        await broadcaster.broadcast_field_update(
            company_id=str(company_id), field_code="kpi_completion", value=pct,
            source_module="kpi", actor_id=str(getattr(user, "id", "")) or None,
        )
    except Exception:
        log.warning("kpi library-sync broadcast failed", exc_info=True)
