"""Governance apply handler (Pack 148-followup B1).

Dispatches by sub.action:
  - "upsert_data"    → mirrors PUT /governance/data
  - "create_member"  → mirrors POST /governance/member
  - "update_member"  → mirrors PATCH /governance/member/{id}
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import and_, select

from app.models.governance import BoardMember, GovernanceData
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.governance import (
    BoardMemberCreate,
    BoardMemberUpdate,
    GovernanceDataEdit,
)
from app.services.moderation_service import register_apply_handler


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()

    if action == "upsert_data":
        payload = GovernanceDataEdit.model_validate(sub.proposed_value)
        d = (await db.execute(
            select(GovernanceData).where(and_(
                GovernanceData.company_id == payload.company_id,
                GovernanceData.year == payload.year,
            ))
        )).scalar_one_or_none()
        if d is None:
            d = GovernanceData(
                company_id=payload.company_id, year=payload.year,
            )
            db.add(d)
        d.board_size = payload.board_size
        d.independent_directors_count = payload.independent_directors_count
        d.women_directors_count = payload.women_directors_count
        d.foreign_directors_count = payload.foreign_directors_count
        d.avg_age = payload.avg_age
        d.has_audit_committee = payload.has_audit_committee
        d.has_remuneration_committee = payload.has_remuneration_committee
        d.has_nomination_committee = payload.has_nomination_committee
        d.has_strategy_committee = payload.has_strategy_committee
        d.meetings_per_year = payload.meetings_per_year
        d.avg_attendance_pct = payload.avg_attendance_pct
        if payload.payload is not None: d.payload = payload.payload
        d.notes = payload.notes
        await db.commit()
        await db.refresh(d)
        return {"action": "upsert_data", "data_id": str(d.id)}

    if action == "create_member":
        payload = BoardMemberCreate.model_validate(sub.proposed_value)
        m = BoardMember(
            company_id=payload.company_id,
            full_name=payload.full_name, position=payload.position,
            role_type=payload.role_type,
            is_independent=payload.is_independent,
            is_woman=payload.is_woman, is_foreign=payload.is_foreign,
            appointed_date=payload.appointed_date,
            term_end_date=payload.term_end_date, bio=payload.bio,
        )
        db.add(m)
        await db.commit()
        await db.refresh(m)
        return {"action": "create_member", "member_id": str(m.id)}

    if action == "update_member":
        if not sub.target_entity_id:
            raise ValueError("missing target_entity_id for update_member")
        try:
            mid = UUID(sub.target_entity_id)
        except Exception as e:
            raise ValueError(f"invalid member id: {sub.target_entity_id}") from e
        m = (await db.execute(
            select(BoardMember).where(BoardMember.id == mid)
        )).scalar_one_or_none()
        if m is None:
            raise ValueError(f"Board member {mid} no longer exists")
        payload = BoardMemberUpdate.model_validate(sub.proposed_value)
        for field in (
            "full_name", "position", "role_type",
            "is_independent", "is_woman", "is_foreign",
            "appointed_date", "term_end_date", "bio",
        ):
            v = getattr(payload, field, None)
            if v is not None:
                setattr(m, field, v)
        await db.commit()
        return {"action": "update_member", "member_id": str(mid)}

    raise ValueError(f"unknown governance action: {action!r}")


register_apply_handler("governance", apply)
