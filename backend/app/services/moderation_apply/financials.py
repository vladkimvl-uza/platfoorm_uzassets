"""Financials apply handler (Pack 148-followup B1).

Applies an approved financial-report save submission. Mirrors PUT /financials/{report_id}
minus the optimistic-concurrency check (the queue itself is the merge point).

Submission shape:
  target_module    = "financials"
  target_entity_id = <report_id UUID string>
  proposed_value   = { "report_id": "<uuid>", ...FinancialReportSavePayload fields... }
"""
from __future__ import annotations

from decimal import Decimal
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

    action = (sub.action or "").lower()

    # ── Редакторы финансов (fin-хвост): каждый диспатчится в apply_submission
    # своего сервиса, который переигрывает тот же write-core от имени автора.
    # ДОЛЖНО быть ВЫШЕ ветки save_report (иначе payload редактора уйдёт в
    # full-replace по report_id и упадёт на FinancialReportSavePayload).
    if action == "nsbu_editor_save":
        from app.services.financials_nsbu.service import apply_submission
        return await apply_submission(db, sub=sub, user=user)
    if action == "ifrs_editor_save":
        from app.services.financials_ifrs.service import apply_submission
        return await apply_submission(db, sub=sub, user=user)
    if action == "hlf_save":
        from app.services.financials_hlf.service import apply_submission
        return await apply_submission(db, sub=sub, user=user)
    if action == "indicators_save":
        from app.services.financials_indicators.service import apply_submission
        return await apply_submission(db, sub=sub, user=user)
    if action in ("detailed_cell", "detailed_mapping",
                  "detailed_delete_line", "detailed_import_confirm"):
        from app.services.financials_detailed.service import apply_submission
        return await apply_submission(db, sub=sub, user=user)

    # ── Точечная запись ОДНОЙ строки из Company Library (mirrors _write_financial).
    # Отдельное действие, чтобы apply НЕ делал full-replace (иначе одна правка через
    # библиотеку затёрла бы все остальные строки отчёта). value уже unit-scaled.
    if (sub.action or "").lower() == "library_line":
        pv = dict(sub.proposed_value)
        report_id_str = pv.get("report_id") or sub.target_entity_id
        line_code = pv.get("line_code")
        if not report_id_str or not line_code:
            raise ValueError("library_line requires report_id + line_code")
        try:
            report_id = UUID(report_id_str)
        except Exception as e:
            raise ValueError(f"invalid report_id: {report_id_str}") from e
        report = (await db.execute(
            select(FinancialReport).where(FinancialReport.id == report_id)
        )).scalar_one_or_none()
        if report is None:
            raise ValueError(f"Financial report {report_id} no longer exists")
        raw = pv.get("value")
        value = None if raw is None else Decimal(str(raw))
        ln = (await db.execute(
            select(FinancialLine).where(
                FinancialLine.report_id == report_id,
                FinancialLine.line_code == line_code,
            )
        )).scalar_one_or_none()
        if ln is None:
            db.add(FinancialLine(
                report_id=report_id, line_code=line_code,
                line_name=pv.get("line_name") or line_code,
                value=value, is_subtotal=False, is_calculated=False,
                sort_order=0, indent_level=0,
            ))
        else:
            ln.value = value
        await db.commit()
        return {"action": "library_line", "report_id": str(report_id), "line_code": line_code}

    # ── Полный save-report (action="save_report" / legacy): delete-and-replace ──
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

    # Защита от затирания: сверяем checksum отчёта на момент открытия автором
    # (payload.expected_prev_checksum) с актуальным — тем же механизмом, что и
    # прямой роут (в moderation-пути он был выключен, что и ловил аудит). Если
    # отчёт изменился после подачи — delete-and-replace затёр бы новые строки.
    if payload.expected_prev_checksum:
        from app.services.financials_reports.service import _compute_checksum
        _cur_lines = (await db.execute(
            select(FinancialLine).where(FinancialLine.report_id == report_id)
        )).scalars().all()
        if _compute_checksum(report, list(_cur_lines)) != payload.expected_prev_checksum:
            raise ValueError(
                "Финотчёт изменился после подачи заявки — применение затёрло бы "
                "новые правки. Отклоните заявку и попросите автора пересоздать "
                "её на актуальных данных.",
            )

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
