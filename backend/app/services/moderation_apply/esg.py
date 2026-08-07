"""ESG apply handler (Pack 148-followup B1).

Dispatches by sub.action:
  - "upsert_metric"        → mirrors PUT  /esg/metric
  - "upsert_maturity_cell" → mirrors PUT  /esg/maturity/cell (матрица зрелости)
  - "create_issue"         → mirrors POST /esg/issue
  - "update_issue"         → mirrors PATCH /esg/issue/{id}
  - "upsert_report"        → mirrors PUT  /esg/report

Delete operations on ESG metrics/issues are not currently gated.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, select

from app.models.esg import ESGIssue, ESGMaturityCell, ESGMetric, ESGReport, ESGSwotItem
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.esg import (
    ESGIssueCreate,
    ESGIssueUpdate,
    ESGMaturityCellUpsert,
    ESGMetricUpsert,
    ESGReportUpsert,
    ESGSwotUpsert,
)
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

    if action == "upsert_maturity_cell":
        # Ячейка матрицы зрелости (D1..D5, D2A заверение, nr/meta служебные).
        # Зеркалит ESGMaturityService.upsert_cell (scope уже проверен при подаче).
        payload = ESGMaturityCellUpsert.model_validate(sub.proposed_value)
        cell = (await db.execute(
            select(ESGMaturityCell).where(and_(
                ESGMaturityCell.company_id == payload.company_id,
                ESGMaturityCell.year == payload.year,
                ESGMaturityCell.dimension == payload.dimension,
                ESGMaturityCell.sub_key == (payload.sub_key or ""),
            ))
        )).scalar_one_or_none()
        if cell is None:
            cell = ESGMaturityCell(
                company_id=payload.company_id, year=payload.year,
                dimension=payload.dimension, sub_key=payload.sub_key or "",
            )
            db.add(cell)
        if payload.stage is not None:
            cell.stage = payload.stage
        if payload.status_text is not None:
            cell.status_text = payload.status_text or None
        if payload.value_text is not None:
            cell.value_text = payload.value_text or None
        if payload.evidence_url is not None:
            cell.evidence_url = payload.evidence_url or None
        if payload.due_date is not None:
            try:
                cell.due_date = date.fromisoformat(payload.due_date) if payload.due_date else None
            except ValueError:
                cell.due_date = None
        if payload.extra is not None:
            cell.extra = payload.extra or None
        cell.last_reviewed_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(cell)
        return {"action": "upsert_maturity_cell", "cell_id": str(cell.id)}

    if action == "upsert_metric":
        payload = ESGMetricUpsert.model_validate(sub.proposed_value)
        m = (await db.execute(
            select(ESGMetric).where(and_(
                ESGMetric.company_id == payload.company_id,
                ESGMetric.year == payload.year,
                ESGMetric.metric_code == payload.metric_code,
            ))
        )).scalar_one_or_none()
        if m is None:
            m = ESGMetric(
                company_id=payload.company_id, year=payload.year,
                pillar=payload.pillar, metric_code=payload.metric_code,
                metric_name=payload.metric_name,
                value=payload.value, unit=payload.unit,
                target=payload.target, benchmark=payload.benchmark,
                notes=payload.notes,
            )
            db.add(m)
        else:
            m.pillar = payload.pillar
            m.metric_name = payload.metric_name
            m.value = payload.value
            m.unit = payload.unit
            m.target = payload.target
            m.benchmark = payload.benchmark
            m.notes = payload.notes
        await db.commit()
        await db.refresh(m)
        return {"action": "upsert_metric", "metric_id": str(m.id)}

    if action == "create_issue":
        # Идемпотентность повтора: id столбим в sub.target_entity_id в том же
        # коммите, что и риск, — повтор применения не плодит дубль.
        if sub.target_entity_id:
            try:
                dup = (await db.execute(
                    select(ESGIssue).where(ESGIssue.id == UUID(sub.target_entity_id))
                )).scalar_one_or_none()
            except Exception:
                dup = None
            if dup is not None:
                return {"action": "create_issue", "issue_id": sub.target_entity_id, "idempotent": True}
        payload = ESGIssueCreate.model_validate(sub.proposed_value)
        issue = ESGIssue(
            company_id=payload.company_id, pillar=payload.pillar,
            title=payload.title, description=payload.description,
            severity=payload.severity, status="open",
        )
        db.add(issue)
        await db.flush()
        sub.target_entity_id = str(issue.id)
        await db.commit()
        await db.refresh(issue)
        return {"action": "create_issue", "issue_id": str(issue.id)}

    if action == "upsert_report":
        payload = ESGReportUpsert.model_validate(sub.proposed_value)
        row = (await db.execute(
            select(ESGReport).where(and_(
                ESGReport.company_id == payload.company_id,
                ESGReport.year == payload.year,
            ))
        )).scalar_one_or_none()
        if row is None:
            row = ESGReport(company_id=payload.company_id, year=payload.year)
            db.add(row)
        if payload.status is not None:
            row.status = (payload.status or "").strip() or None
        if payload.report_url is not None:
            row.report_url = (payload.report_url or "").strip() or None
        if payload.note is not None:
            row.note = (payload.note or "").strip() or None
        row.changed_by = getattr(user, "id", None)
        row.changed_by_name = getattr(user, "full_name", None) or getattr(user, "email", None)
        await db.commit()
        await db.refresh(row)
        return {"action": "upsert_report", "report_id": str(row.id)}

    if action == "update_issue":
        if not sub.target_entity_id:
            raise ValueError("missing target_entity_id for update_issue")
        try:
            iid = UUID(sub.target_entity_id)
        except Exception as e:
            raise ValueError(f"invalid issue id: {sub.target_entity_id}") from e
        i = (await db.execute(
            select(ESGIssue).where(ESGIssue.id == iid)
        )).scalar_one_or_none()
        if i is None:
            raise ValueError(f"ESG issue {iid} no longer exists")
        payload = ESGIssueUpdate.model_validate(sub.proposed_value)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(i, field, value)
        await db.commit()
        return {"action": "update_issue", "issue_id": str(iid)}

    if action == "upsert_swot":
        # Ветки не было, хотя роут PUT /esg/swot гейтится модерацией, —
        # одобренная заявка внешнего автора падала «unknown esg action».
        payload = ESGSwotUpsert.model_validate(sub.proposed_value)
        item = None
        if payload.id is not None:
            item = (await db.execute(
                select(ESGSwotItem).where(ESGSwotItem.id == payload.id)
            )).scalar_one_or_none()
        if item is None:
            item = ESGSwotItem(kind=payload.kind, scope=payload.scope)
            # Автор — тот, кто ПРЕДЛОЖИЛ вывод, а не модератор, который нажал
            # «принять»: подпись «кто добавил» должна вести к автору заявки.
            proposer = (await db.execute(
                select(User).where(User.id == sub.proposer_user_id)
            )).scalar_one_or_none()
            if proposer is not None:
                from app.services.esg.maturity_service import ESGMaturityService
                _uid, _name, _title, _org = await ESGMaturityService.swot_author_snapshot(
                    db, proposer,
                )
                item.created_by = _uid
                item.created_by_name = _name
                item.created_by_title = _title
                item.created_by_org = _org
            db.add(item)
        item.kind = payload.kind
        item.scope = payload.scope
        item.company_id = payload.company_id if payload.scope == "company" else None
        item.title = payload.title
        item.body = payload.body
        item.severity = payload.severity
        item.order_idx = payload.order_idx
        await db.commit()
        return {"action": "upsert_swot", "item_id": str(item.id)}

    if action == "delete_swot":
        if not sub.target_entity_id:
            raise ValueError("missing target_entity_id for delete_swot")
        try:
            sid = UUID(sub.target_entity_id)
        except Exception as e:
            raise ValueError(f"invalid swot id: {sub.target_entity_id}") from e
        item = (await db.execute(
            select(ESGSwotItem).where(ESGSwotItem.id == sid)
        )).scalar_one_or_none()
        if item is None:
            # Уже удалён — считаем применённым, а не падаем: заявка могла
            # висеть, пока вывод убрали напрямую.
            return {"action": "delete_swot", "item_id": str(sid), "already_gone": True}
        await db.delete(item)
        await db.commit()
        return {"action": "delete_swot", "item_id": str(sid)}

    raise ValueError(f"unknown esg action: {action!r}")


register_apply_handler("esg", apply)
