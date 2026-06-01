"""Financials apply handler (Pack 148-followup B1).

Applies an approved financial-report save submission. Mirrors PUT /financials/{report_id}
minus the optimistic-concurrency check (the queue itself is the merge point).

Submission shape:
  target_module    = "financials"
  target_entity_id = <report_id UUID string>
  proposed_value   = { "report_id": "<uuid>", ...FinancialReportSavePayload fields... }
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select

from app.models.financial import FinancialLine, FinancialReport
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.financial import FinancialReportSavePayload
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)
    report_id_str = pv.pop("report_id", None) or sub.target_entity_id
    if not report_id_str:
        raise ValueError("missing report_id in proposed_value / target_entity_id")
    try:
        report_id = UUID(report_id_str)
    except Exception as e:
        raise ValueError(f"invalid report_id: {report_id_str}") from e

    try:
        payload = FinancialReportSavePayload.model_validate(pv)
    except Exception as e:
        raise ValueError(f"proposed_value does not match FinancialReportSavePayload: {e}") from e

    report = (await db.execute(
        select(FinancialReport).where(FinancialReport.id == report_id)
    )).scalar_one_or_none()
    if report is None:
        raise ValueError(f"Financial report {report_id} no longer exists")

    # Apply header
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

    await db.execute(delete(FinancialLine).where(FinancialLine.report_id == report_id))

    n_lines = 0
    for ln in payload.lines:
        db.add(FinancialLine(
            report_id=report_id,
            line_code=ln.line_code, line_name=ln.line_name,
            line_name_uz=ln.line_name_uz, line_name_en=ln.line_name_en,
            parent_code=ln.parent_code, value=ln.value,
            is_subtotal=ln.is_subtotal, is_calculated=ln.is_calculated,
            sort_order=ln.sort_order,
        ))
        n_lines += 1

    await db.commit()
    return {"report_id": str(report_id), "lines_written": n_lines}


register_apply_handler("financials", apply)
