"""ESG apply handler (Pack 148-followup B1).

Dispatches by sub.action:
  - "upsert_metric"  → mirrors PUT  /esg/metric
  - "create_issue"   → mirrors POST /esg/issue
  - "update_issue"   → mirrors PATCH /esg/issue/{id}

Delete operations on ESG metrics/issues are not currently gated.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select

from app.models.esg import ESGIssue, ESGMetric
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.esg import ESGIssueCreate, ESGIssueUpdate, ESGMetricUpsert
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

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
        payload = ESGIssueCreate.model_validate(sub.proposed_value)
        issue = ESGIssue(
            company_id=payload.company_id, pillar=payload.pillar,
            title=payload.title, description=payload.description,
            severity=payload.severity, status="open",
        )
        db.add(issue)
        await db.commit()
        await db.refresh(issue)
        return {"action": "create_issue", "issue_id": str(issue.id)}

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

    raise ValueError(f"unknown esg action: {action!r}")


register_apply_handler("esg", apply)
