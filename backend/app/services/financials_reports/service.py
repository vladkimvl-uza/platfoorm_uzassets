"""Financials reports CRUD use-cases (catalog + list/get/create/save/delete).

Owns:
  - Catalog loading + caching
  - Checksum computation (anti-loss)
  - Hydration of FinancialReportFull
  - All header/lines CRUD on the canonical `financial_reports` table

Detailed/NSBU/IFRS/HLF/Portfolio sections remain in `routes/financials.py`
pending follow-up extraction (TODO).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import allowed_company_ids
from app.core.audit_chain import append_audit_entry
from app.core.i18n import current_locale, tr
from app.core.security import has_effective_permission
from app.models.financial import FinancialLine, FinancialReport
from app.models.user import User
from app.repositories.financials_repository import FinancialsRepository
from app.schemas.financial import (
    CatalogResponse,
    FinancialLineCatalogEntry,
    FinancialLineEdit,
    FinancialReportCreatePayload,
    FinancialReportFull,
    FinancialReportListItem,
    FinancialReportSavePayload,
    FinancialReportSaveResponse,
)

# ─── Library-sync helper J) ───────────────────────────────

_FIN_LINE_TO_FIELD = {
    "revenue":             "revenue",
    "выручка":             "revenue",
    "ebitda":              "ebitda",
    "EBITDA":              "ebitda",
    "profit":              "net_profit",
    "net_profit":          "net_profit",
    "profit_for_the_year": "net_profit",
    "netProfit":           "net_profit",
    "debt":                "total_debt",
    "totalDebt":           "total_debt",
    "total_debt":          "total_debt",
    "totalAssets":         "total_assets",
    "total_assets":        "total_assets",
    "equity":              "equity",
    "total_equity":        "total_equity",
}


async def _broadcast_finmodel_fields(report, line_objs, user) -> None:
    try:
        from app.services.sync_broadcaster import broadcaster
        if (report.standard or "").upper() != "IFRS":
            return
        if (report.report_type or "").upper() not in ("PL", "BS"):
            return
        scale = report.unit_scale or 1
        cid = str(report.company_id)
        actor_id = str(getattr(user, "id", "")) or None
        seen: dict[str, float | None] = {}
        for ln in line_objs:
            fc = _FIN_LINE_TO_FIELD.get(ln.line_code)
            if fc is None or fc in seen:
                continue
            v = ln.value
            if v is None:
                seen[fc] = None
                continue
            try:
                seen[fc] = float(v) * scale
            except (TypeError, ValueError):
                continue
        for fc, val in seen.items():
            await broadcaster.broadcast_field_update(
                company_id=cid, field_code=fc, value=val,
                source_module="finmodel", actor_id=actor_id,
            )
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "finmodel library-sync broadcast failed", exc_info=True
        )


# ─── Catalog (loaded lazily) ──────────────────────────────────────

_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "data" / "seed" / "financial_lines_catalog.json"
)
_CATALOG_CACHE: Optional[list[FinancialLineCatalogEntry]] = None


def _load_catalog() -> list[FinancialLineCatalogEntry]:
    if not _CATALOG_PATH.exists():
        return []
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return [FinancialLineCatalogEntry(**r) for r in raw]


def get_catalog() -> list[FinancialLineCatalogEntry]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        _CATALOG_CACHE = _load_catalog()
    return _CATALOG_CACHE


# ─── Checksum ─────────────────────────────────────────────────────

def _compute_checksum(
    report: FinancialReport, lines: list[FinancialLine]
) -> str:
    """Deterministic checksum over header + sorted lines. Used for
    optimistic concurrency + verify-after-save."""
    parts: list[str] = [
        f"{report.year}|{report.quarter or ''}|{report.standard}|{report.report_type}",
        f"{report.currency}|{report.unit_scale}|{int(report.is_audited)}",
    ]
    sorted_lines = sorted(lines, key=lambda l: (l.line_code or "", l.sort_order))
    for ln in sorted_lines:
        if ln.value is None:
            v = ""
        else:
            normalized = Decimal(ln.value).quantize(Decimal("0.0001"))
            v = format(normalized, "f")
        parts.append(f"{ln.line_code}|{v}|{ln.sort_order}")
    blob = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:32]


@dataclass
class FinancialsReportsService:
    """Operates on raw `AsyncSession` because of moderation gates and
    multi-commit audit semantics — keeps txn boundaries unchanged."""

    @staticmethod
    def _repo(db: AsyncSession) -> FinancialsRepository:
        return FinancialsRepository(db)

    async def _hydrate(
        self, db: AsyncSession, report: FinancialReport
    ) -> FinancialReportFull:
        repo = self._repo(db)
        lines = await repo.list_report_lines(report.id)
        co = await repo.get_company_brief(report.company_id)
        checksum = _compute_checksum(report, lines)
        return FinancialReportFull(
            id=report.id, company_id=report.company_id,
            company_code=co.code if co else "",
            company_name=co.name_short if co else None,
            year=report.year, quarter=report.quarter,
            standard=report.standard, report_type=report.report_type,
            currency=report.currency, unit_scale=report.unit_scale,
            source=report.source, is_audited=report.is_audited,
            notes=report.notes, extra=report.extra,
            lines=[FinancialLineEdit(
                line_code=ln.line_code, line_name=ln.line_name,
                line_name_uz=ln.line_name_uz, line_name_en=ln.line_name_en,
                parent_code=ln.parent_code, value=ln.value,
                is_subtotal=ln.is_subtotal, is_calculated=ln.is_calculated,
                sort_order=ln.sort_order,
            ) for ln in lines],
            created_at=report.created_at, updated_at=report.updated_at,
            checksum=checksum,
        )

    async def _require_view(self, db: AsyncSession, user: User) -> None:
        if not await has_effective_permission(db, user, "financials.view"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.view",
            )

    async def _require_edit(self, db: AsyncSession, user: User) -> None:
        if not await has_effective_permission(db, user, "financials.edit"):
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Permission required: financials.edit",
            )

    # ─── Catalog ──────────────────────────────────────────────────

    async def get_financials_catalog(
        self, db: AsyncSession, user: User
    ) -> CatalogResponse:
        await self._require_view(db, user)
        return CatalogResponse(line_codes=get_catalog())

    # ─── List / Get ───────────────────────────────────────────────

    async def list_reports(
        self,
        db: AsyncSession,
        user: User,
        *,
        company_code: Optional[str] = None,
        year: Optional[int] = None,
        standard: Optional[str] = None,
        limit: int = 100,
    ) -> list[FinancialReportListItem]:
        await self._require_view(db, user)
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and len(scope_ids) == 0:
            return []
        rows = await self._repo(db).list_reports(
            company_code=company_code, year=year, standard=standard,
            limit=limit, allowed_company_ids=scope_ids,
        )
        return [
            FinancialReportListItem(
                id=r.FinancialReport.id,
                company_code=r.co_code,
                year=r.FinancialReport.year,
                quarter=r.FinancialReport.quarter,
                standard=r.FinancialReport.standard,
                report_type=r.FinancialReport.report_type,
                is_audited=r.FinancialReport.is_audited,
                lines_count=r.lines_count or 0,
                updated_at=r.FinancialReport.updated_at,
            )
            for r in rows
        ]

    async def get_report(
        self, report_id: UUID, db: AsyncSession, user: User
    ) -> FinancialReportFull:
        await self._require_view(db, user)
        repo = self._repo(db)
        report = await repo.get_report(report_id)
        if not report:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Financial report not found"
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and report.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this report"
            )
        return await self._hydrate(db, report)

    # ─── Create / Save / Delete ───────────────────────────────────

    async def create_report(
        self,
        payload: FinancialReportCreatePayload,
        db: AsyncSession,
        user: User,
    ) -> FinancialReportFull:
        await self._require_edit(db, user)
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and payload.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN,
                "Cannot create financial report for a company outside your allowed list",
            )
        repo = self._repo(db)
        company = await repo.get_company(payload.company_id)
        if not company:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST, "Company not found"
            )
        if await repo.find_duplicate_report(
            company_id=payload.company_id, year=payload.year,
            quarter=payload.quarter, standard=payload.standard,
            report_type=payload.report_type,
        ):
            raise HTTPException(
                http_status.HTTP_409_CONFLICT,
                f"Report for {company.code} {payload.year}/{payload.standard}/{payload.report_type} already exists.",
            )
        report = FinancialReport(
            company_id=payload.company_id,
            year=payload.year, quarter=payload.quarter,
            standard=payload.standard, report_type=payload.report_type,
            currency=payload.currency, unit_scale=payload.unit_scale,
            source=payload.source, is_audited=False,
        )
        repo.add(report)
        await db.commit()
        await repo.refresh(report)

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="financials.create",
            entity_type="financial_report", entity_id=str(report.id),
            notes=f"{company.code} {payload.year} {payload.standard}/{payload.report_type}",
        )
        await db.commit()
        return await self._hydrate(db, report)

    async def save_report(
        self,
        report_id: UUID,
        payload: FinancialReportSavePayload,
        db: AsyncSession,
        user: User,
    ) -> tuple[Optional[FinancialReportSaveResponse], Optional[dict]]:
        """Returns either (response, None) for the normal happy path, or
        (None, queued_dict) if moderation gate held the change."""
        await self._require_edit(db, user)
        repo = self._repo(db)
        report = await repo.get_report(report_id)
        if not report:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Financial report not found"
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and report.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this report"
            )

        # Moderation gate
        from app.services.moderation_service import gate_or_apply
        queued, sub = await gate_or_apply(
            db, user=user,
            module="financials", action="save_report",
            entity_id=str(report_id),
            entity_label=f"Финотчёт {payload.standard} {payload.year} Q{payload.quarter or ''}",
            company_id=report.company_id, sector_id=None, year=payload.year,
            payload={"report_id": str(report_id), **payload.model_dump(mode="json")},
            diff_summary=f"Сохранение финотчёта · {len(payload.lines)} строк",
        )
        if queued:
            return None, {
                "queued": True, "submission_id": str(sub.id),
                "status": sub.status,
                "message": tr("Изменение отправлено на модерацию", current_locale()),
            }

        if payload.expected_prev_checksum:
            old_lines = await repo.list_report_lines(report_id)
            current_checksum = _compute_checksum(report, old_lines)
            if current_checksum != payload.expected_prev_checksum:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    "The report was modified by someone else since you opened it. "
                    "Please refresh and re-apply your changes.",
                )

        report.year         = payload.year
        report.quarter      = payload.quarter
        report.standard     = payload.standard
        report.report_type  = payload.report_type
        report.currency     = payload.currency
        report.unit_scale   = payload.unit_scale
        report.source       = payload.source
        report.is_audited   = payload.is_audited
        report.notes        = payload.notes
        report.extra        = payload.extra

        await repo.delete_report_lines(report_id)
        new_line_objs: list[FinancialLine] = []
        for ln in payload.lines:
            obj = FinancialLine(
                report_id=report_id,
                line_code=ln.line_code, line_name=ln.line_name,
                line_name_uz=ln.line_name_uz, line_name_en=ln.line_name_en,
                parent_code=ln.parent_code, value=ln.value,
                is_subtotal=ln.is_subtotal, is_calculated=ln.is_calculated,
                sort_order=ln.sort_order,
            )
            new_line_objs.append(obj)
            repo.add(obj)
        await repo.flush()

        new_checksum = _compute_checksum(report, new_line_objs)

        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="financials.save",
            entity_type="financial_report", entity_id=str(report_id),
            notes=f"lines={len(new_line_objs)}, checksum={new_checksum[:16]}",
        )
        await db.commit()
        await repo.refresh(report)

        await _broadcast_finmodel_fields(report, new_line_objs, user)

        full = await self._hydrate(db, report)
        return FinancialReportSaveResponse(
            report=full,
            saved_at=datetime.now(UTC),
            lines_total=len(new_line_objs),
            server_checksum=new_checksum,
        ), None

    async def bulk_add_lines(
        self, rows: list[dict], db: AsyncSession, user: User,
    ) -> dict:
        """Аддитивное создание строк финотчётов из ИИ-импорта (минуя модерацию).

        rows[i]: {company_id: UUID, year:int, quarter:Optional[int],
                  standard:'IFRS'|'NSBU', report_type:'PL'|'BS'|'CF',
                  currency:str, unit_scale:int, article:str, value:Optional[Decimal]}.
        Группирует по (company, year, quarter, standard, report_type) → get-or-create
        отчёт → добавляет строки в конец (line_code продолжается), НЕ затирая существующие.
        """
        from collections import OrderedDict

        await self._require_edit(db, user)
        repo = self._repo(db)

        groups: "OrderedDict[tuple, list[dict]]" = OrderedDict()
        for r in rows:
            key = (r["company_id"], r["year"], r.get("quarter"), r["standard"], r["report_type"])
            groups.setdefault(key, []).append(r)

        reports_touched = 0
        lines_added = 0
        for (cid, year, quarter, standard, rtype), grp in groups.items():
            report = await repo.find_duplicate_report(
                company_id=cid, year=year, quarter=quarter,
                standard=standard, report_type=rtype,
            )
            if report is None:
                report = FinancialReport(
                    company_id=cid, year=year, quarter=quarter,
                    standard=standard, report_type=rtype,
                    currency=grp[0].get("currency") or "UZS",
                    # канон платформы: value в МЛРД → unit_scale=1e9 (аудит P1)
                    unit_scale=grp[0].get("unit_scale") or 1_000_000_000,
                    source="import",
                )
                repo.add(report)
                await repo.flush()      # populate report.id
                base = 0
            else:
                base = len(await repo.list_report_lines(report.id))

            for i, r in enumerate(grp):
                name = str(r.get("article") or "").strip()
                if not name:
                    continue
                repo.add(FinancialLine(
                    report_id=report.id,
                    line_code=str(base + i + 1),
                    line_name=name[:512],
                    value=r.get("value"),
                    sort_order=base + i,
                ))
                lines_added += 1
            reports_touched += 1

        await db.commit()
        return {"reports": reports_touched, "lines_added": lines_added}

    async def delete_report(
        self, report_id: UUID, db: AsyncSession, user: User
    ) -> None:
        await self._require_edit(db, user)
        repo = self._repo(db)
        report = await repo.get_report(report_id)
        if not report:
            raise HTTPException(
                http_status.HTTP_404_NOT_FOUND, "Financial report not found"
            )
        scope_ids = await allowed_company_ids(db, user)
        if scope_ids is not None and report.company_id not in scope_ids:
            raise HTTPException(
                http_status.HTTP_403_FORBIDDEN, "No access to this report"
            )
        co_code = (await repo.get_company_code(report.company_id)) or "?"
        year, std, rtyp = report.year, report.standard, report.report_type
        await repo.delete(report)
        await db.commit()
        await append_audit_entry(
            db, actor_id=str(user.id), actor_email=user.email,
            action="financials.delete",
            entity_type="financial_report", entity_id=str(report_id),
            notes=f"{co_code} {year} {std}/{rtyp}",
        )
        await db.commit()
