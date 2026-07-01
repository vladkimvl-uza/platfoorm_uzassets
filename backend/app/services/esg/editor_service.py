"""ESG company-detail queries + metric/issue mutations."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.esg import ESGIssue, ESGMetric
from app.schemas.esg import (
    ESGCompanyDetail,
    ESGIssueBrief,
    ESGIssueCreate,
    ESGIssueUpdate,
    ESGMetricBrief,
    ESGMetricUpsert,
)
from app.services.esg._helpers import (
    company_score_from_metrics,
    issue_to_brief,
    metric_to_brief,
)
from app.uow.ports import UnitOfWorkABC


class ESGCompanyService:
    """Read-only: per-company detail."""

    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def get_company_detail(
        self,
        company_id: UUID,
        *,
        year: Optional[int],
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGCompanyDetail:
        async with self.uow:
            co = await self.uow.esg.get_company_with_sector(
                company_id, scope_company_ids=scope_company_ids,
            )
            if not co:
                raise HTTPException(404, detail="Company not found")
            available_years = await self.uow.esg.company_metric_years(company_id)
            target_year = year or (available_years[0] if available_years else datetime.now().year)
            metrics = await self.uow.esg.list_company_metrics(company_id, target_year)
            issues = await self.uow.esg.list_company_issues(company_id)
            tracked = await self.uow.esg.active_tracked_years(company_id)

        metrics_e = [metric_to_brief(m, co.code) for m in metrics if m.pillar == "E"]
        metrics_s = [metric_to_brief(m, co.code) for m in metrics if m.pillar == "S"]
        metrics_g = [metric_to_brief(m, co.code) for m in metrics if m.pillar == "G"]
        scores = company_score_from_metrics(metrics)
        issues_brief = [issue_to_brief(i, co.code, co.name_short or co.name_ru) for i in issues]

        return ESGCompanyDetail(
            company_id=co.id, company_code=co.code, company_name=co.name_short or co.name_ru,
            sector_code=(co.sector.code if co.sector else None),
            year=target_year,
            e_score=scores["E"], s_score=scores["S"], g_score=scores["G"],
            overall_score=scores["overall"],
            metrics_e=metrics_e, metrics_s=metrics_s, metrics_g=metrics_g,
            issues=issues_brief,
            available_years=available_years, tracked_years=tracked,
        )


class ESGEditorService:
    """Metric and issue CRUD."""

    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── metrics ──────────────────────────────────────────────────

    async def upsert_metric(
        self,
        payload: ESGMetricUpsert,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGMetricBrief:
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, detail="No access to this company")

        async with self.uow:
            m = await self.uow.esg.get_metric_for_unique(
                payload.company_id, payload.year, payload.metric_code,
            )
            if m is None:
                m = ESGMetric(
                    company_id=payload.company_id, year=payload.year,
                    pillar=payload.pillar, metric_code=payload.metric_code,
                    metric_name=payload.metric_name,
                    value=payload.value, unit=payload.unit,
                    target=payload.target, benchmark=payload.benchmark,
                    notes=payload.notes,
                )
                self.uow.esg.add(m)
            else:
                m.pillar = payload.pillar
                m.metric_name = payload.metric_name
                m.value = payload.value
                m.unit = payload.unit
                m.target = payload.target
                m.benchmark = payload.benchmark
                m.notes = payload.notes
            await self.uow.esg.flush()
            await self.uow.esg.refresh(m)
            return metric_to_brief(m)

    async def delete_metric(
        self,
        metric_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> None:
        async with self.uow:
            m = await self.uow.esg.get_metric(metric_id)
            if not m:
                return  # idempotent
            if scope_company_ids is not None and m.company_id not in scope_company_ids:
                raise HTTPException(403, detail="Forbidden")
            await self.uow.esg.delete(m)
            await self.uow.esg.flush()

    # ─── issues ───────────────────────────────────────────────────

    async def list_issues(
        self,
        *,
        company_id: Optional[UUID],
        pillar: Optional[str],
        severity: Optional[str],
        status: Optional[str],
        limit: int,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> list[ESGIssueBrief]:
        async with self.uow:
            rows = await self.uow.esg.list_issues_filtered(
                company_id=company_id, pillar=pillar,
                severity=severity, status=status,
                scope_company_ids=scope_company_ids, limit=limit,
            )
            if not rows:
                return []
            co_lookup = await self.uow.esg.companies_by_ids(
                list({r.company_id for r in rows})
            )

        return [
            issue_to_brief(
                r,
                co_lookup[r.company_id].code if r.company_id in co_lookup else None,
                (co_lookup[r.company_id].name_short or co_lookup[r.company_id].name_ru) if r.company_id in co_lookup else None,
            )
            for r in rows
        ]

    async def get_issue_for_moderation(
        self,
        issue_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGIssue:
        async with self.uow:
            i = await self.uow.esg.get_issue(issue_id)
        if not i:
            raise HTTPException(404, detail="Issue not found")
        if scope_company_ids is not None and i.company_id not in scope_company_ids:
            raise HTTPException(403, detail="Forbidden")
        return i

    async def create_issue(
        self,
        payload: ESGIssueCreate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGIssueBrief:
        if scope_company_ids is not None and payload.company_id not in scope_company_ids:
            raise HTTPException(403, detail="Forbidden")
        async with self.uow:
            issue = ESGIssue(
                company_id=payload.company_id,
                pillar=payload.pillar,
                title=payload.title,
                description=payload.description,
                severity=payload.severity,
                status="open",
            )
            self.uow.esg.add(issue)
            await self.uow.esg.flush()
            await self.uow.esg.refresh(issue)
            co = await self.uow.esg.get_company(issue.company_id)
            return issue_to_brief(
                issue,
                co.code if co else None,
                (co.name_short or co.name_ru) if co else None,
            )

    async def update_issue(
        self,
        issue_id: UUID,
        payload: ESGIssueUpdate,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGIssueBrief:
        async with self.uow:
            i = await self.uow.esg.get_issue(issue_id)
            if not i:
                raise HTTPException(404, detail="Issue not found")
            if scope_company_ids is not None and i.company_id not in scope_company_ids:
                raise HTTPException(403, detail="Forbidden")
            if payload.pillar is not None:      i.pillar = payload.pillar
            if payload.title is not None:       i.title = payload.title
            if payload.description is not None: i.description = payload.description
            if payload.severity is not None:    i.severity = payload.severity
            if payload.status is not None:      i.status = payload.status
            await self.uow.esg.flush()
            await self.uow.esg.refresh(i)
            co = await self.uow.esg.get_company(i.company_id)
            return issue_to_brief(
                i,
                co.code if co else None,
                (co.name_short or co.name_ru) if co else None,
            )

    async def delete_issue(
        self,
        issue_id: UUID,
        *,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> None:
        async with self.uow:
            i = await self.uow.esg.get_issue(issue_id)
            if not i:
                return  # idempotent
            if scope_company_ids is not None and i.company_id not in scope_company_ids:
                raise HTTPException(403, detail="Forbidden")
            await self.uow.esg.delete(i)
            await self.uow.esg.flush()
