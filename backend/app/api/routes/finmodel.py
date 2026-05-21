"""FinModel v2 REST API — Phase 1.5.

Mounted at /finmodel via main.py loader. Endpoints follow handoff §1.5.
Permission: `finmodel.view` for reads, `finmodel.edit` for writes.

NOTE on isolation (handoff Decision 1): module reads `companies` table for
naming only. No FKs to KPI/Credit/Library — pure financial-truth storage.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status as http_status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import has_effective_permission
from app.database import get_db
from app.models.company import Company
from app.models.finmodel import (
    FinModelAuditLog, FinModelCellComment, FinModelCellValue,
    FinModelMacroCompany, FinModelMacroGlobal, FinModelScenario,
    FinModelTemplateRow, FinModelYearLock,
)
from app.models.user import User
from app.schemas.finmodel import (
    AuditEntry, AuditList, CellBatchWrite, CellValueRead, CellWrite,
    CommentCreate, CommentRead, ForecastRequest, MacroCompanyWrite,
    MacroEffective, MacroGlobalRead, ScenarioCreate, ScenarioRead,
    TemplateRowRead, ValidationIssue, YearDataRead, YearLockRead, YearLockUpdate,
)
from app.services.finmodel_engine import FormulaEngine
from app.services.finmodel_importer import build_commit_payload, parse_excel
from app.services.finmodel_validator import validate as run_validation


router = APIRouter(prefix="/finmodel", tags=["finmodel-v2"])


# ─── Helpers ─────────────────────────────────────────────────────────
async def _require(user: User, db: AsyncSession, perm: str) -> None:
    if not await has_effective_permission(db, user, perm):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"{perm} required")


async def _load_template(db: AsyncSession) -> List[FinModelTemplateRow]:
    q = await db.execute(select(FinModelTemplateRow).order_by(FinModelTemplateRow.section, FinModelTemplateRow.order_idx))
    return list(q.scalars().all())


async def _load_year_cells(db: AsyncSession, company_id: UUID, year: int) -> List[FinModelCellValue]:
    q = await db.execute(
        select(FinModelCellValue).where(
            and_(FinModelCellValue.company_id == company_id, FinModelCellValue.year == year)
        )
    )
    return list(q.scalars().all())


async def _ensure_company(db: AsyncSession, company_id: UUID) -> Company:
    c = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if c is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Company {company_id} not found")
    return c


async def _is_year_locked(db: AsyncSession, company_id: UUID, year: int) -> bool:
    lock = (await db.execute(
        select(FinModelYearLock).where(
            and_(FinModelYearLock.company_id == company_id, FinModelYearLock.year == year)
        )
    )).scalar_one_or_none()
    return bool(lock and lock.status in ("locked", "approved"))


async def _resolve_macro(db: AsyncSession, company_id: UUID, year: int) -> MacroEffective:
    """Company-override first, fall back to global. Per-field tracking."""
    co_q = await db.execute(
        select(FinModelMacroCompany).where(
            and_(FinModelMacroCompany.company_id == company_id, FinModelMacroCompany.year == year)
        )
    )
    co = co_q.scalar_one_or_none()
    gl_q = await db.execute(select(FinModelMacroGlobal).where(FinModelMacroGlobal.year == year))
    gl = gl_q.scalar_one_or_none()

    out = MacroEffective(year=year)
    for field in ("uz_inflation", "us_inflation", "uzs_usd_avg_rate", "uzs_eur_avg_rate", "uzs_rub_avg_rate", "uzs_cny_avg_rate"):
        if co and getattr(co, field, None) is not None:
            setattr(out, field, getattr(co, field))
            out.source[field] = "company"
        elif gl and getattr(gl, field, None) is not None:
            setattr(out, field, getattr(gl, field))
            out.source[field] = "global"
        else:
            out.source[field] = "none"
    return out


async def _log_audit(
    db: AsyncSession, *, company_id: UUID, year: int, row_code: str,
    value_before: Optional[Decimal], value_after: Optional[Decimal],
    actor_id: Optional[UUID], source: str,
) -> None:
    db.add(FinModelAuditLog(
        company_id=company_id, year=year, row_code=row_code,
        value_before=value_before, value_after=value_after,
        actor_id=actor_id, source=source,
    ))


# ═══════════════════════════════════════════════════════════════════
# READ ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.get("/template", response_model=List[TemplateRowRead])
async def get_template(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """All 105 template rows (cached client-side, static after seed)."""
    return await _load_template(db)


# ─── Specific-path GET endpoints — MUST be declared before generic
# `/{company_id}/{year}` and `/{company_id}` routes, otherwise FastAPI's
# in-order matching captures them as path-param values and returns 422.
# (Bug fix from audit: /macro/global, /{co}/scenarios, /{co}/comments.)

@router.get("/macro/global", response_model=List[MacroGlobalRead])
async def list_macro_global(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.view")
    q = await db.execute(select(FinModelMacroGlobal).order_by(FinModelMacroGlobal.year))
    return [MacroGlobalRead.model_validate(r) for r in q.scalars().all()]


@router.get("/{company_id}/scenarios", response_model=List[ScenarioRead])
async def list_scenarios(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.view")
    q = await db.execute(
        select(FinModelScenario).where(FinModelScenario.company_id == company_id).order_by(FinModelScenario.created_at.desc())
    )
    return [ScenarioRead.model_validate(s) for s in q.scalars().all()]


@router.get("/{company_id}/comments", response_model=List[CommentRead])
async def list_comments(
    company_id: UUID, year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.view")
    q = select(FinModelCellComment).where(FinModelCellComment.company_id == company_id)
    if year is not None:
        q = q.where(FinModelCellComment.year == year)
    q = q.order_by(FinModelCellComment.created_at.desc())
    return [CommentRead.model_validate(c) for c in (await db.execute(q)).scalars().all()]


@router.get("/{company_id}", response_model=List[YearLockRead])
async def list_years(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Years for a company with their lock states. Years come from cell_values + year_lock union."""
    await _require(user, db, "finmodel.view")
    await _ensure_company(db, company_id)
    # Distinct years from cells
    cell_years_q = await db.execute(
        select(FinModelCellValue.year).where(FinModelCellValue.company_id == company_id).distinct()
    )
    cell_years = {row[0] for row in cell_years_q.all()}
    lock_q = await db.execute(
        select(FinModelYearLock).where(FinModelYearLock.company_id == company_id)
    )
    locks = {l.year: l for l in lock_q.scalars().all()}
    all_years = sorted(cell_years | set(locks.keys()))
    out: List[YearLockRead] = []
    for y in all_years:
        if y in locks:
            out.append(YearLockRead.model_validate(locks[y]))
        else:
            out.append(YearLockRead(year=y, status="draft"))
    return out


@router.get("/{company_id}/{year}", response_model=YearDataRead)
async def get_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full data for one year: cells (only stored ones — engine fills the rest client-side),
    macro (effective: company override + global fallback), lock state, balance check."""
    await _require(user, db, "finmodel.view")
    await _ensure_company(db, company_id)
    cells = await _load_year_cells(db, company_id, year)
    macro = await _resolve_macro(db, company_id, year)
    lock = (await db.execute(
        select(FinModelYearLock).where(
            and_(FinModelYearLock.company_id == company_id, FinModelYearLock.year == year)
        )
    )).scalar_one_or_none()
    lock_data = YearLockRead.model_validate(lock) if lock else YearLockRead(year=year, status="draft")

    # Run engine to compute balance check
    template = await _load_template(db)
    engine = FormulaEngine(template)
    input_values = {c.row_code: c.value for c in cells if c.value is not None}
    computed = engine.compute_all(input_values)
    balance = engine.balance_check(computed)

    return YearDataRead(
        company_id=company_id,
        year=year,
        lock=lock_data,
        macro=macro,
        cells=[CellValueRead.model_validate(c) for c in cells],
        balance_check=balance,
    )


@router.get("/{company_id}/{year}/export.csv")
async def export_year_csv(
    company_id: UUID,
    year: int,
    include_macro: bool = Query(True, description="Append macro assumptions section"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream the full single-year model as CSV. Includes:
    - Header row: section,code,name,row_type,value,is_input,formula
    - All NSBU rows (BS + PL) with engine-computed values for subtotals/grands/checks
    - Optional macro-assumptions trailer block

    M11 handoff says Excel + PDF are also planned; CSV ships first as universal baseline.
    """
    await _require(user, db, "finmodel.view")
    await _ensure_company(db, company_id)

    template = await _load_template(db)
    cells = await _load_year_cells(db, company_id, year)
    engine = FormulaEngine(template)
    input_values = {c.row_code: c.value for c in cells if c.value is not None}
    computed = engine.compute_all(input_values)

    # Build CSV in-memory — single year, ~105 rows, negligible memory cost
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "code", "name_ru", "row_type", "value", "is_input", "formula"])
    for r in template:
        v = computed.get(r.code)
        v_str = "" if v is None else str(v)
        w.writerow([
            r.section, r.code, r.name_ru, r.row_type, v_str,
            "1" if r.row_type == "input" else "0",
            r.formula or "",
        ])

    if include_macro:
        macro = await _resolve_macro(db, company_id, year)
        w.writerow([])
        w.writerow(["macro", "field", "value", "source"])
        for fld in ("uz_inflation", "us_inflation", "uzs_usd_avg_rate", "uzs_eur_avg_rate", "uzs_rub_avg_rate", "uzs_cny_avg_rate"):
            val = getattr(macro, fld, None)
            src = macro.source.get(fld, "none") if hasattr(macro, "source") and macro.source else "none"
            w.writerow(["macro", fld, "" if val is None else str(val), src])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM helps Excel detect UTF-8
    filename = f"finmodel_{company_id}_{year}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{company_id}/{year}/audit", response_model=AuditList)
async def get_audit(
    company_id: UUID,
    year: int,
    row_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.view")
    q = select(FinModelAuditLog).where(
        and_(FinModelAuditLog.company_id == company_id, FinModelAuditLog.year == year)
    )
    if row_code:
        q = q.where(FinModelAuditLog.row_code == row_code)
    total_q = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_q.scalar_one() or 0
    items_q = await db.execute(q.order_by(FinModelAuditLog.ts.desc()).limit(limit))
    items = [AuditEntry.model_validate(x) for x in items_q.scalars().all()]
    return AuditList(items=items, total=total)


@router.get("/{company_id}/{year}/validate", response_model=List[ValidationIssue])
async def validate_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.view")
    cells = await _load_year_cells(db, company_id, year)
    template = await _load_template(db)
    engine = FormulaEngine(template)
    inputs = {c.row_code: c.value for c in cells if c.value is not None}
    computed = engine.compute_all(inputs)
    return run_validation(computed)


# ═══════════════════════════════════════════════════════════════════
# WRITE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@router.patch("/{company_id}/{year}/cell", response_model=CellValueRead)
async def patch_cell(
    company_id: UUID,
    year: int,
    body: CellWrite,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    if await _is_year_locked(db, company_id, year):
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Год {year} заблокирован — снимите блокировку")

    # Validate row_code exists in template + is input-type (subtotals are computed)
    row = (await db.execute(
        select(FinModelTemplateRow).where(FinModelTemplateRow.code == body.row_code)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Unknown row_code: {body.row_code}")
    if row.row_type != "input":
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Row {body.row_code} is computed ({row.row_type}), cannot edit directly")

    cell = (await db.execute(
        select(FinModelCellValue).where(and_(
            FinModelCellValue.company_id == company_id,
            FinModelCellValue.year == year,
            FinModelCellValue.row_code == body.row_code,
        ))
    )).scalar_one_or_none()

    value_before = cell.value if cell else None
    if cell:
        cell.value = body.value
        cell.updated_by = user.id
    else:
        cell = FinModelCellValue(
            company_id=company_id, year=year, row_code=body.row_code,
            value=body.value, is_calculated=False, updated_by=user.id,
        )
        db.add(cell)

    await _log_audit(
        db, company_id=company_id, year=year, row_code=body.row_code,
        value_before=value_before, value_after=body.value,
        actor_id=user.id, source="manual",
    )
    await db.commit()
    await db.refresh(cell)
    return CellValueRead.model_validate(cell)


@router.patch("/{company_id}/{year}/cells/batch", response_model=List[CellValueRead])
async def patch_cells_batch(
    company_id: UUID,
    year: int,
    body: CellBatchWrite,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    if await _is_year_locked(db, company_id, year):
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Год {year} заблокирован")

    # Pre-validate all codes
    template = await _load_template(db)
    rows_by_code = {r.code: r for r in template}
    for c in body.cells:
        r = rows_by_code.get(c.row_code)
        if r is None:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Unknown row_code: {c.row_code}")
        if r.row_type != "input":
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, f"Row {c.row_code} is computed, cannot edit")

    # Existing cells map
    existing_q = await db.execute(
        select(FinModelCellValue).where(and_(
            FinModelCellValue.company_id == company_id,
            FinModelCellValue.year == year,
            FinModelCellValue.row_code.in_([c.row_code for c in body.cells]),
        ))
    )
    existing_by_code = {x.row_code: x for x in existing_q.scalars().all()}

    out_cells: List[FinModelCellValue] = []
    for c in body.cells:
        cell = existing_by_code.get(c.row_code)
        prev = cell.value if cell else None
        if cell:
            cell.value = c.value
            cell.updated_by = user.id
        else:
            cell = FinModelCellValue(
                company_id=company_id, year=year, row_code=c.row_code,
                value=c.value, is_calculated=False, updated_by=user.id,
            )
            db.add(cell)
        out_cells.append(cell)
        await _log_audit(
            db, company_id=company_id, year=year, row_code=c.row_code,
            value_before=prev, value_after=c.value,
            actor_id=user.id, source="manual",
        )
    await db.commit()
    for c in out_cells:
        await db.refresh(c)
    return [CellValueRead.model_validate(c) for c in out_cells]


@router.get("/{company_id}/{year}/macro", response_model=MacroEffective)
async def get_macro(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Effective macro for (company, year) = company override merged over global default."""
    await _require(user, db, "finmodel.view")
    await _ensure_company(db, company_id)
    return await _resolve_macro(db, company_id, year)


@router.put("/{company_id}/{year}/macro", response_model=MacroEffective)
async def put_macro(
    company_id: UUID,
    year: int,
    body: MacroCompanyWrite,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    if await _is_year_locked(db, company_id, year):
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Год {year} заблокирован")
    existing = (await db.execute(
        select(FinModelMacroCompany).where(and_(
            FinModelMacroCompany.company_id == company_id,
            FinModelMacroCompany.year == year,
        ))
    )).scalar_one_or_none()
    fields = ("uz_inflation", "us_inflation", "uzs_usd_avg_rate",
              "forecast_method", "manual_growth_pct", "dividend_payout_ratio")
    if existing:
        for f in fields:
            v = getattr(body, f, None)
            if v is not None:
                setattr(existing, f, v)
        existing.updated_by = user.id
    else:
        kwargs = {f: getattr(body, f, None) for f in fields}
        kwargs["company_id"] = company_id
        kwargs["year"] = year
        kwargs["updated_by"] = user.id
        db.add(FinModelMacroCompany(**kwargs))
    await db.commit()
    return await _resolve_macro(db, company_id, year)


# ═══════════════════════════════════════════════════════════════════
# YEAR LIFECYCLE
# ═══════════════════════════════════════════════════════════════════

@router.post("/{company_id}/year/{year}", response_model=YearLockRead, status_code=http_status.HTTP_201_CREATED)
async def create_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Initialize empty year (no cells). Creates draft year_lock row."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    existing = (await db.execute(
        select(FinModelYearLock).where(and_(
            FinModelYearLock.company_id == company_id, FinModelYearLock.year == year
        ))
    )).scalar_one_or_none()
    if existing:
        return YearLockRead.model_validate(existing)
    lock = FinModelYearLock(company_id=company_id, year=year, status="draft")
    db.add(lock)
    await db.commit()
    await db.refresh(lock)
    return YearLockRead.model_validate(lock)


@router.delete("/{company_id}/year/{year}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_year(
    company_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hard-delete all data for one (company, year): cells + macro_company + lock + comments."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    if await _is_year_locked(db, company_id, year):
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Год {year} заблокирован — снимите блокировку перед удалением")
    await db.execute(delete(FinModelCellValue).where(and_(
        FinModelCellValue.company_id == company_id, FinModelCellValue.year == year
    )))
    await db.execute(delete(FinModelMacroCompany).where(and_(
        FinModelMacroCompany.company_id == company_id, FinModelMacroCompany.year == year
    )))
    await db.execute(delete(FinModelYearLock).where(and_(
        FinModelYearLock.company_id == company_id, FinModelYearLock.year == year
    )))
    await db.execute(delete(FinModelCellComment).where(and_(
        FinModelCellComment.company_id == company_id, FinModelCellComment.year == year
    )))
    await _log_audit(db, company_id=company_id, year=year, row_code="*",
                     value_before=None, value_after=None,
                     actor_id=user.id, source="manual_year_delete")
    await db.commit()


@router.post("/{company_id}/year/{year}/copy-from/{src_year}", response_model=YearLockRead)
async def copy_year(
    company_id: UUID, year: int, src_year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Copy all input cells from src_year → year. Overwrites existing target year."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    if await _is_year_locked(db, company_id, year):
        raise HTTPException(http_status.HTTP_409_CONFLICT, f"Год {year} заблокирован")
    src_cells = await _load_year_cells(db, company_id, src_year)
    if not src_cells:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"В исходном году {src_year} нет данных")

    # Clear target year cells
    await db.execute(delete(FinModelCellValue).where(and_(
        FinModelCellValue.company_id == company_id, FinModelCellValue.year == year
    )))
    for sc in src_cells:
        if sc.value is None:
            continue
        db.add(FinModelCellValue(
            company_id=company_id, year=year, row_code=sc.row_code,
            value=sc.value, is_calculated=False, updated_by=user.id,
        ))
        await _log_audit(db, company_id=company_id, year=year, row_code=sc.row_code,
                         value_before=None, value_after=sc.value,
                         actor_id=user.id, source=f"copy_from_{src_year}")

    # Ensure year_lock row exists
    lock = (await db.execute(
        select(FinModelYearLock).where(and_(
            FinModelYearLock.company_id == company_id, FinModelYearLock.year == year
        ))
    )).scalar_one_or_none()
    if not lock:
        lock = FinModelYearLock(company_id=company_id, year=year, status="draft")
        db.add(lock)
    await db.commit()
    await db.refresh(lock)
    return YearLockRead.model_validate(lock)


@router.post("/{company_id}/year/{year}/lock", response_model=YearLockRead)
async def lock_year(
    company_id: UUID, year: int, body: YearLockUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    lock = (await db.execute(
        select(FinModelYearLock).where(and_(
            FinModelYearLock.company_id == company_id, FinModelYearLock.year == year
        ))
    )).scalar_one_or_none()
    if not lock:
        lock = FinModelYearLock(company_id=company_id, year=year, status=body.status,
                                approval_note=body.approval_note,
                                locked_at=datetime.utcnow(), locked_by=user.id)
        db.add(lock)
    else:
        lock.status = body.status
        lock.approval_note = body.approval_note
        lock.locked_at = datetime.utcnow()
        lock.locked_by = user.id
    await db.commit()
    await db.refresh(lock)
    return YearLockRead.model_validate(lock)


@router.post("/{company_id}/year/{year}/unlock", response_model=YearLockRead)
async def unlock_year(
    company_id: UUID, year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set status=draft (admin perm required)."""
    await _require(user, db, "finmodel.admin")
    lock = (await db.execute(
        select(FinModelYearLock).where(and_(
            FinModelYearLock.company_id == company_id, FinModelYearLock.year == year
        ))
    )).scalar_one_or_none()
    if not lock:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Year lock not found")
    lock.status = "draft"
    lock.locked_at = None
    lock.locked_by = None
    await db.commit()
    await db.refresh(lock)
    return YearLockRead.model_validate(lock)


# ═══════════════════════════════════════════════════════════════════
# SCENARIOS (snapshot+restore)
# ═══════════════════════════════════════════════════════════════════

@router.post("/{company_id}/scenarios", response_model=ScenarioRead, status_code=http_status.HTTP_201_CREATED)
async def create_scenario(
    company_id: UUID, body: ScenarioCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Snapshot ALL current cells + macro_company for this company into a named scenario."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    cells_q = await db.execute(
        select(FinModelCellValue).where(FinModelCellValue.company_id == company_id)
    )
    macro_q = await db.execute(
        select(FinModelMacroCompany).where(FinModelMacroCompany.company_id == company_id)
    )
    snapshot = {
        "cells": [{"year": c.year, "row_code": c.row_code, "value": (str(c.value) if c.value is not None else None)} for c in cells_q.scalars().all()],
        "macro": [{
            "year": m.year,
            "uz_inflation": str(m.uz_inflation) if m.uz_inflation is not None else None,
            "us_inflation": str(m.us_inflation) if m.us_inflation is not None else None,
            "uzs_usd_avg_rate": str(m.uzs_usd_avg_rate) if m.uzs_usd_avg_rate is not None else None,
            "forecast_method": m.forecast_method,
            "manual_growth_pct": str(m.manual_growth_pct) if m.manual_growth_pct is not None else None,
            "dividend_payout_ratio": str(m.dividend_payout_ratio) if m.dividend_payout_ratio is not None else None,
        } for m in macro_q.scalars().all()],
    }
    s = FinModelScenario(
        company_id=company_id, name=body.name, description=body.description,
        is_active=False, snapshot_data=snapshot, created_by=user.id,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return ScenarioRead.model_validate(s)


@router.post("/{company_id}/scenarios/{scenario_id}/activate", response_model=ScenarioRead)
async def activate_scenario(
    company_id: UUID, scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Restore snapshot_data into cells + macro_company.
    WARNING: overwrites existing draft data — confirmation required in UI."""
    await _require(user, db, "finmodel.edit")
    s = (await db.execute(
        select(FinModelScenario).where(and_(
            FinModelScenario.id == scenario_id, FinModelScenario.company_id == company_id
        ))
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Scenario not found")

    # Get all years from snapshot that are NOT locked — apply only those
    years_in_snap = {c["year"] for c in (s.snapshot_data.get("cells") or [])}
    locks_q = await db.execute(
        select(FinModelYearLock).where(and_(
            FinModelYearLock.company_id == company_id,
            FinModelYearLock.year.in_(years_in_snap),
        ))
    )
    locked_years = {l.year for l in locks_q.scalars().all() if l.status in ("locked", "approved")}
    applicable_years = years_in_snap - locked_years

    # Clear cells in applicable years
    await db.execute(delete(FinModelCellValue).where(and_(
        FinModelCellValue.company_id == company_id,
        FinModelCellValue.year.in_(applicable_years),
    )))
    # Replay cells
    for c in s.snapshot_data.get("cells", []):
        if c["year"] not in applicable_years:
            continue
        v = Decimal(c["value"]) if c["value"] is not None else None
        db.add(FinModelCellValue(
            company_id=company_id, year=c["year"], row_code=c["row_code"],
            value=v, is_calculated=False, updated_by=user.id,
        ))
        await _log_audit(db, company_id=company_id, year=c["year"], row_code=c["row_code"],
                         value_before=None, value_after=v,
                         actor_id=user.id, source="scenario_load")

    # Replay macro_company
    await db.execute(delete(FinModelMacroCompany).where(and_(
        FinModelMacroCompany.company_id == company_id,
        FinModelMacroCompany.year.in_(applicable_years),
    )))
    for m in s.snapshot_data.get("macro", []):
        if m["year"] not in applicable_years:
            continue
        kwargs = {"company_id": company_id, "year": m["year"], "updated_by": user.id}
        for f in ("uz_inflation", "us_inflation", "uzs_usd_avg_rate", "manual_growth_pct", "dividend_payout_ratio"):
            kwargs[f] = Decimal(m[f]) if m.get(f) is not None else None
        kwargs["forecast_method"] = m.get("forecast_method") or "uz_inflation"
        db.add(FinModelMacroCompany(**kwargs))

    # Deactivate all, activate this one
    await db.execute(
        FinModelScenario.__table__.update()
        .where(FinModelScenario.company_id == company_id)
        .values(is_active=False)
    )
    s.is_active = True
    await db.commit()
    await db.refresh(s)
    return ScenarioRead.model_validate(s)


@router.delete("/{company_id}/scenarios/{scenario_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    company_id: UUID, scenario_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    await db.execute(delete(FinModelScenario).where(and_(
        FinModelScenario.id == scenario_id, FinModelScenario.company_id == company_id
    )))
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# COMMENTS
# ═══════════════════════════════════════════════════════════════════

@router.post("/{company_id}/{year}/comment", response_model=CommentRead, status_code=http_status.HTTP_201_CREATED)
async def add_comment(
    company_id: UUID, year: int, body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    c = FinModelCellComment(
        company_id=company_id, year=year, row_code=body.row_code,
        comment_text=body.comment_text, source_ref=body.source_ref,
        author_id=user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return CommentRead.model_validate(c)


@router.delete("/{company_id}/{year}/comment/{comment_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_comment(
    company_id: UUID, year: int, comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _require(user, db, "finmodel.edit")
    await db.execute(delete(FinModelCellComment).where(and_(
        FinModelCellComment.id == comment_id,
        FinModelCellComment.company_id == company_id,
    )))
    await db.commit()


# ═══════════════════════════════════════════════════════════════════
# FORECAST (Phase 1.9)
# ═══════════════════════════════════════════════════════════════════

PL_INPUT_CODES_FOR_FORECAST = [
    "PL_010", "PL_020", "PL_050", "PL_060", "PL_070", "PL_080",
    "PL_120", "PL_130", "PL_140", "PL_150", "PL_160",
    "PL_180", "PL_190", "PL_200", "PL_210", "PL_230",
    "PL_250", "PL_260",
]


# ─── Excel import (M3 handoff) ──────────────────────────────────────
class ImportCommitRequest(BaseModel):
    preview: dict
    selected_years: Optional[List[int]] = None
    skip_unmatched: bool = True


@router.post("/{company_id}/import-excel/preview", response_model=dict)
async def import_excel_preview(
    company_id: UUID,
    file: UploadFile = File(...),
    sheet: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Parse .xlsx and return preview JSON (no DB writes). Frontend M3 wizard
    shows the preview, lets user pick which years to commit, then calls
    /import-excel/commit with the structure."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Ожидается .xlsx или .xlsm файл")
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 10MB")
    template = await _load_template(db)
    known_codes = {r.code for r in template}
    try:
        return parse_excel(raw, known_codes, sheet_name=sheet)
    except Exception as e:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, f"Не удалось разобрать файл: {e}")


@router.post("/{company_id}/import-excel/commit", response_model=dict)
async def import_excel_commit(
    company_id: UUID,
    body: ImportCommitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Apply a previously-previewed parse. Returns {inserted, updated, skipped_locked_years}."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    triples = build_commit_payload(
        body.preview, selected_years=body.selected_years, skip_unmatched=body.skip_unmatched,
    )
    if not triples:
        return {"inserted": 0, "updated": 0, "skipped_locked_years": []}

    inserted = 0
    updated = 0
    skipped_locked: List[int] = []
    # Group by year for batched lock-check
    years = {y for (y, _, _) in triples}
    locked_years: Set[int] = set()
    for y in years:
        if await _is_year_locked(db, company_id, y):
            locked_years.add(y)
            skipped_locked.append(y)
        else:
            # Ensure year_lock row exists (so the year is visible)
            existing_lock = (await db.execute(
                select(FinModelYearLock).where(and_(
                    FinModelYearLock.company_id == company_id, FinModelYearLock.year == y,
                ))
            )).scalar_one_or_none()
            if not existing_lock:
                db.add(FinModelYearLock(company_id=company_id, year=y, status="draft"))

    for (year, code, value_str) in triples:
        if year in locked_years:
            continue
        existing = (await db.execute(
            select(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id,
                FinModelCellValue.year == year,
                FinModelCellValue.row_code == code,
            ))
        )).scalar_one_or_none()
        try:
            new_v = Decimal(value_str)
        except Exception:
            continue
        if existing:
            prev = existing.value
            existing.value = new_v
            existing.updated_by = user.id
            existing.is_calculated = False
            await _log_audit(db, company_id=company_id, year=year, row_code=code,
                             value_before=prev, value_after=new_v,
                             actor_id=user.id, source="excel_import")
            updated += 1
        else:
            db.add(FinModelCellValue(
                company_id=company_id, year=year, row_code=code,
                value=new_v, is_calculated=False, updated_by=user.id,
            ))
            await _log_audit(db, company_id=company_id, year=year, row_code=code,
                             value_before=None, value_after=new_v,
                             actor_id=user.id, source="excel_import")
            inserted += 1
    await db.commit()
    return {"inserted": inserted, "updated": updated, "skipped_locked_years": sorted(set(skipped_locked))}


@router.post("/{company_id}/forecast", response_model=dict)
async def regenerate_forecast(
    company_id: UUID, body: ForecastRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """For each target year, apply growth (uz_inflation | manual | cagr_5y from base_year P&L lines)."""
    await _require(user, db, "finmodel.edit")
    await _ensure_company(db, company_id)
    base_cells_q = await db.execute(
        select(FinModelCellValue).where(and_(
            FinModelCellValue.company_id == company_id, FinModelCellValue.year == body.base_year,
        ))
    )
    base_by_code = {c.row_code: c.value for c in base_cells_q.scalars().all() if c.value is not None}
    if not base_by_code:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Базовый год {body.base_year} пуст")

    counts: dict = {"updated": 0, "skipped_locked_years": []}
    for ty in body.target_years:
        if await _is_year_locked(db, company_id, ty):
            counts["skipped_locked_years"].append(ty)
            continue
        macro = await _resolve_macro(db, company_id, ty)
        if body.method == "uz_inflation":
            growth = (macro.uz_inflation or Decimal("0")) + Decimal("1")
        elif body.method == "manual":
            co_macro = (await db.execute(
                select(FinModelMacroCompany).where(and_(
                    FinModelMacroCompany.company_id == company_id, FinModelMacroCompany.year == ty,
                ))
            )).scalar_one_or_none()
            growth = (co_macro.manual_growth_pct if co_macro and co_macro.manual_growth_pct else Decimal("0")) + Decimal("1")
        else:  # cagr_5y — fallback to 1.0 (no-op for now)
            growth = Decimal("1")

        existing_q = await db.execute(
            select(FinModelCellValue).where(and_(
                FinModelCellValue.company_id == company_id, FinModelCellValue.year == ty,
                FinModelCellValue.row_code.in_(PL_INPUT_CODES_FOR_FORECAST),
            ))
        )
        existing_by_code = {x.row_code: x for x in existing_q.scalars().all()}

        for code in PL_INPUT_CODES_FOR_FORECAST:
            base = base_by_code.get(code)
            if base is None:
                continue
            new_v = (Decimal(base) * growth).quantize(Decimal("0.01"))
            cell = existing_by_code.get(code)
            prev = cell.value if cell else None
            if cell:
                cell.value = new_v
                cell.updated_by = user.id
                cell.is_calculated = True
            else:
                db.add(FinModelCellValue(
                    company_id=company_id, year=ty, row_code=code,
                    value=new_v, is_calculated=True, updated_by=user.id,
                ))
            await _log_audit(db, company_id=company_id, year=ty, row_code=code,
                             value_before=prev, value_after=new_v,
                             actor_id=user.id, source="forecast")
            counts["updated"] += 1
    await db.commit()
    return counts
