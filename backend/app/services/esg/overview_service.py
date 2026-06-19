"""ESG Overview dashboard composer.

The legacy `get_overview` was 316 LOC of pillar/severity/rankings/kpis/
sectors/recent-updates aggregation. Here it's broken into 6 named methods
each <50 LOC so the overall flow is readable from top to bottom.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Optional
from uuid import UUID

from app.models.agency_rating import AgencyRating
from app.models.company import Company
from app.models.esg import ESGIssue, ESGMetric
from app.schemas.esg import (
    AgencyCoverageStat,
    AgencyRatingCell,
    ESGCompanyScore,
    ESGOverviewKpis,
    ESGOverviewResponse,
    IssueSeverityStat,
    PillarStat,
    RecentRatingUpdate,
    SectorBreakdownItem,
)
from app.services.esg._helpers import (
    AGENCY_COLORS,
    ESG_OVERVIEW_AGENCIES,
    PILLARS,
    SEVERITY_META,
    attainment_pct,
    benchmark_diff_pct,
    company_abbr,
    company_score_from_metrics,
    esg_rating_to_score,
    esg_score_to_letter,
    is_recent_rating,
    sector_fallback_color,
    sector_label,
)
from app.uow.ports import UnitOfWorkABC


class ESGOverviewService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def get_overview(
        self,
        *,
        year: Optional[int],
        sector_code: Optional[str],
        rankings_limit: int,
        scope_company_ids: Optional[Sequence[UUID]],
    ) -> ESGOverviewResponse:
        async with self.uow:
            metrics = await self.uow.esg.list_metrics(
                year=year, sector_code=sector_code,
                scope_company_ids=scope_company_ids,
            )
            issues = await self.uow.esg.list_issues_for_overview(
                sector_code=sector_code, scope_company_ids=scope_company_ids,
            )
            companies = await self.uow.esg.list_companies(
                sector_code=sector_code, scope_company_ids=scope_company_ids,
            )
            ratings = await self.uow.esg.list_esg_ratings(
                scope_company_ids=scope_company_ids,
            )
            yrs = await self.uow.esg.all_metric_years()
            sectors = await self.uow.esg.sectors_with_counts()

        # Index ratings by company
        ratings_by_co: dict[UUID, dict[str, AgencyRating]] = {}
        for r in ratings:
            ratings_by_co.setdefault(r.company_id, {})[r.agency] = r

        # Bucket metrics/issues by company
        metrics_by_co: dict[UUID, list[ESGMetric]] = {}
        for m in metrics:
            metrics_by_co.setdefault(m.company_id, []).append(m)
        issues_by_co: dict[UUID, list[ESGIssue]] = {}
        for i in issues:
            issues_by_co.setdefault(i.company_id, []).append(i)

        pillars = self._build_pillars(metrics)
        sev_split, open_count, crit_count = self._build_severity(issues)
        rankings, composite_scores, recent_updates_payload = self._build_rankings(
            companies, metrics_by_co, issues_by_co, ratings_by_co,
        )
        list(rankings)
        rankings = rankings[:rankings_limit]

        kpis = self._build_kpis(
            companies=companies, metrics=metrics, metrics_by_co=metrics_by_co,
            rankings=rankings, composite_scores=composite_scores,
            open_count=open_count, crit_count=crit_count,
            ratings_by_co=ratings_by_co,
        )
        # ВАЖНО: ratings грузятся без sector_code (только RBAC-scope), поэтому
        # ratings_by_co — портфельный. Для донат-покрытия считаем ТОЛЬКО по
        # компаниям текущей выборки (сектор-фильтр), иначе при фильтре получаем
        # «10 из 5» / 200% — агентские счётчики шире отфильтрованного total.
        agency_coverage = self._build_agency_coverage(
            ratings_by_co, {co.id for co in companies},
        )
        sector_breakdown = self._build_sector_breakdown(rankings)
        recent_updates = self._build_recent_updates(recent_updates_payload)

        return ESGOverviewResponse(
            year=year, sector_code=sector_code,
            kpis=kpis, pillars=pillars,
            issue_severity_split=sev_split, rankings=rankings,
            agency_coverage=agency_coverage,
            sector_breakdown=sector_breakdown,
            recent_updates=recent_updates,
            available_years=yrs, sectors=sectors,
            generated_at=datetime.now(UTC),
        )

    # ─── pillars ──────────────────────────────────────────────────

    @staticmethod
    def _build_pillars(metrics: list[ESGMetric]) -> list[PillarStat]:
        pillars: list[PillarStat] = []
        for p in PILLARS:
            p_metrics = [m for m in metrics if m.pillar == p]
            co_set = {m.company_id for m in p_metrics}
            attainments, bench_diffs = [], []
            on_target = behind = 0
            for m in p_metrics:
                att = attainment_pct(m.value, m.target)
                if att is not None:
                    attainments.append(att)
                    if att >= 100:
                        on_target += 1
                    else:
                        behind += 1
                bd = benchmark_diff_pct(m.value, m.benchmark)
                if bd is not None:
                    bench_diffs.append(bd)
            pillars.append(PillarStat(
                pillar=p,
                metric_count=len(p_metrics),
                company_count=len(co_set),
                avg_target_attainment=round(sum(attainments) / len(attainments), 1) if attainments else None,
                avg_benchmark_diff=round(sum(bench_diffs) / len(bench_diffs), 1) if bench_diffs else None,
                on_target_count=on_target,
                behind_count=behind,
            ))
        return pillars

    # ─── severity ─────────────────────────────────────────────────

    @staticmethod
    def _build_severity(issues: list[ESGIssue]) -> tuple[list[IssueSeverityStat], int, int]:
        sev_buckets = {meta["key"]: 0 for meta in SEVERITY_META}
        open_count = crit_count = 0
        for i in issues:
            if i.severity in sev_buckets:
                sev_buckets[i.severity] += 1
            if i.status == "open":
                open_count += 1
            if i.severity == "critical" and i.status != "closed":
                crit_count += 1
        split = [
            IssueSeverityStat(
                severity=meta["key"], label=meta["label"], color=meta["color"],
                count=sev_buckets.get(meta["key"], 0),
            )
            for meta in SEVERITY_META
        ]
        return split, open_count, crit_count

    # ─── rankings ─────────────────────────────────────────────────

    @staticmethod
    def _build_rankings(
        companies: list[Company],
        metrics_by_co: dict[UUID, list[ESGMetric]],
        issues_by_co: dict[UUID, list[ESGIssue]],
        ratings_by_co: dict[UUID, dict[str, AgencyRating]],
    ) -> tuple[list[ESGCompanyScore], list[tuple[Company, float]], list[tuple[Company, AgencyRating]]]:
        rankings: list[ESGCompanyScore] = []
        composite_scores: list[tuple[Company, float]] = []
        recent_updates_payload: list[tuple[Company, AgencyRating]] = []

        for co in companies:
            co_metrics = metrics_by_co.get(co.id, [])
            scores = company_score_from_metrics(co_metrics)
            co_issues = issues_by_co.get(co.id, [])
            years_set = {m.year for m in co_metrics}
            last_year = max(years_set) if years_set else None

            sec_code = co.sector.code if co.sector else None
            sector_color = (
                co.primary_color
                or (co.sector.color_hex if co.sector else None)
                or sector_fallback_color(sec_code)
            )

            co_ratings = ratings_by_co.get(co.id, {})
            cells: list[AgencyRatingCell] = []
            co_composite_parts: list[float] = []
            co_recent = 0
            for ag in ESG_OVERVIEW_AGENCIES:
                ar = co_ratings.get(ag)
                if ar is None:
                    cells.append(AgencyRatingCell(agency=ag))
                    continue
                is_recent = is_recent_rating(ar.rating_date_text, ar.rating_date)
                if is_recent:
                    co_recent += 1
                    recent_updates_payload.append((co, ar))
                cells.append(AgencyRatingCell(
                    agency=ag, rating_id=ar.id, rating=ar.rating, score=ar.score, outlook=ar.outlook,
                    rating_date_text=ar.rating_date_text, report_url=ar.report_url,
                    is_recent=is_recent,
                ))
                s = esg_rating_to_score(ar.rating)
                if s is not None:
                    co_composite_parts.append(s)

            composite = (sum(co_composite_parts) / len(co_composite_parts)) if co_composite_parts else None
            has_any = any(c.rating for c in cells)
            if composite is not None:
                composite_scores.append((co, composite))

            rankings.append(ESGCompanyScore(
                company_id=co.id, company_code=co.code, company_name=co.name_ru,
                company_abbr=company_abbr(co), sector_code=sec_code, sector_color=sector_color,
                e_score=scores["E"], s_score=scores["S"], g_score=scores["G"],
                overall_score=scores["overall"],
                metric_count=len(co_metrics),
                issues_open=sum(1 for i in co_issues if i.status == "open"),
                issues_critical=sum(1 for i in co_issues if i.severity == "critical"),
                last_year_reported=last_year,
                ratings_by_agency=cells,
                composite_esg_score=round(composite, 2) if composite is not None else None,
                has_any_rating=has_any,
                recent_updates_count=co_recent,
            ))

        def _rank_sort_key(r: ESGCompanyScore):
            primary = r.composite_esg_score if r.composite_esg_score is not None else (
                r.overall_score / 10 if r.overall_score is not None else None
            )
            return (primary is None, -(primary or 0))

        rankings.sort(key=_rank_sort_key)
        for idx, r in enumerate(rankings):
            r.rank = idx + 1
        return rankings, composite_scores, recent_updates_payload

    # ─── KPIs ─────────────────────────────────────────────────────

    @staticmethod
    def _build_kpis(
        *,
        companies: list[Company],
        metrics: list[ESGMetric],
        metrics_by_co: dict[UUID, list[ESGMetric]],
        rankings: list[ESGCompanyScore],
        composite_scores: list[tuple[Company, float]],
        open_count: int,
        crit_count: int,
        ratings_by_co: dict[UUID, dict[str, AgencyRating]],
    ) -> ESGOverviewKpis:
        overall_scores = [r.overall_score for r in rankings if r.overall_score is not None]
        covered = sum(1 for r in rankings if r.has_any_rating)
        total = len(companies)
        coverage_pct = round(100 * covered / total) if total else 0
        unrated = total - covered
        recent_total = sum(r.recent_updates_count for r in rankings)

        leader_co = leader_comp = None
        if composite_scores:
            composite_scores_sorted = sorted(composite_scores, key=lambda x: -x[1])
            leader_co, leader_comp = composite_scores_sorted[0]
        leader_ratings = 0
        if leader_co is not None:
            leader_ratings = sum(
                1 for c in (ratings_by_co.get(leader_co.id) or {}).values()
                if c.agency in ESG_OVERVIEW_AGENCIES
            )

        return ESGOverviewKpis(
            total_companies=total,
            companies_with_data=len(metrics_by_co),
            metrics_total=len(metrics),
            issues_open=open_count,
            issues_critical=crit_count,
            avg_overall_score=round(sum(overall_scores) / len(overall_scores), 1) if overall_scores else None,
            covered_count=covered,
            coverage_pct=coverage_pct,
            leader_company_id=leader_co.id if leader_co else None,
            leader_company_name=leader_co.name_ru if leader_co else None,
            leader_composite=round(leader_comp, 2) if leader_comp is not None else None,
            leader_rating_letter=esg_score_to_letter(leader_comp) if leader_comp is not None else None,
            leader_ratings_count=leader_ratings,
            unrated_count=unrated,
            recent_updates_count=recent_total,
        )

    # ─── agency coverage donut ────────────────────────────────────

    @staticmethod
    def _build_agency_coverage(
        ratings_by_co: dict[UUID, dict[str, AgencyRating]],
        company_ids: set[UUID] | None = None,
    ) -> list[AgencyCoverageStat]:
        agency_coverage: list[AgencyCoverageStat] = []
        for ag in ESG_OVERVIEW_AGENCIES:
            cnt = sum(
                1 for co_id in ratings_by_co
                if (company_ids is None or co_id in company_ids)
                and ag in ratings_by_co[co_id] and ratings_by_co[co_id][ag].rating
            )
            agency_coverage.append(AgencyCoverageStat(
                agency=ag, count=cnt, color=AGENCY_COLORS.get(ag, "#888780"),
            ))
        return agency_coverage

    # ─── sector breakdown ─────────────────────────────────────────

    @staticmethod
    def _build_sector_breakdown(rankings: list[ESGCompanyScore]) -> list[SectorBreakdownItem]:
        by_sector: dict[str, list[ESGCompanyScore]] = {}
        for r in rankings:
            key = r.sector_code or "other"
            by_sector.setdefault(key, []).append(r)
        out: list[SectorBreakdownItem] = []
        for sec_code, rows in by_sector.items():
            rated = [r for r in rows if r.composite_esg_score is not None]
            if rated:
                top = max(rated, key=lambda r: r.composite_esg_score or 0)
                top_co_id, top_name, top_comp = top.company_id, top.company_name, top.composite_esg_score
            else:
                top_co_id = top_name = top_comp = None
            out.append(SectorBreakdownItem(
                code=sec_code, label=sector_label(sec_code),
                color=sector_fallback_color(sec_code),
                total=len(rows),
                covered=sum(1 for r in rows if r.has_any_rating),
                coverage_pct=round(100 * sum(1 for r in rows if r.has_any_rating) / len(rows)) if rows else 0,
                leader_company_id=top_co_id,
                leader_company_name=top_name,
                leader_composite=top_comp,
            ))
        out.sort(key=lambda s: (-s.coverage_pct, -s.total))
        return out

    # ─── recent updates ───────────────────────────────────────────

    @staticmethod
    def _build_recent_updates(
        payload: list[tuple[Company, AgencyRating]],
    ) -> list[RecentRatingUpdate]:
        payload.sort(key=lambda t: (t[1].rating_date or date.min), reverse=True)
        out: list[RecentRatingUpdate] = []
        for co, ar in payload[:10]:
            sec_code = co.sector.code if co.sector else None
            out.append(RecentRatingUpdate(
                company_id=co.id, company_code=co.code,
                company_name=co.name_ru or co.code,
                sector_code=sec_code,
                sector_color=(co.primary_color
                              or (co.sector.color_hex if co.sector else None)
                              or sector_fallback_color(sec_code)),
                agency=ar.agency,
                agency_color=AGENCY_COLORS.get(ar.agency, "#888780"),
                rating=ar.rating, score=ar.score,
                rating_date_text=ar.rating_date_text,
                report_url=ar.report_url,
            ))
        return out
