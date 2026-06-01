"""Use cases for Credit Scenarios — CRUD + overview + drilldowns.

Heavy compute lives in existing core `app/services/credit_scenario_engine.py`
(compute_state_summary / debt_ratios / repayment_forecast / top_loans) —
not touched. `_aggregate_impl` from credit_portfolio.py (also untouched)
is the source of truth for overview KPIs.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date as _date
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.credit_scenario import (
    CUSTOM_INDICATOR_AGGREGATIONS,
    CUSTOM_INDICATOR_INPUT_TYPES,
    CreditCustomIndicator,
    CreditPortfolioLoanScenario,
    CreditPortfolioScenario,
)
from app.schemas.credit_scenario import (
    CreditPortfolioScenarioCreate,
    CreditPortfolioScenarioUpdate,
    CustomIndicatorCreate,
    CustomIndicatorUpdate,
    FormulaTestResponse,
    LoanScenarioUpdate,
)
from app.services.credit_scenario._helpers import (
    CURRENCY_LABELS_RU,
    DEFAULT_PD_BY_LENDER,
    DEFAULT_RR_BY_LENDER,
    KNOWN_CURRENCIES,
    LENDER_LABELS_RU,
    MATURITY_LABELS,
)
from app.uow.ports import UnitOfWorkABC


class CreditScenarioService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── scenarios CRUD ───────────────────────────────────────────

    async def list_scenarios(self):
        async with self.uow:
            return await self.uow.credit_scenario.list_scenarios()

    async def get_scenario(self, scenario_id: UUID):
        async with self.uow:
            sc = await self.uow.credit_scenario.get_scenario(scenario_id)
            if not sc:
                raise HTTPException(404, "Scenario not found")
            return sc

    async def create_scenario(
        self, body: CreditPortfolioScenarioCreate, *, actor_id: UUID,
    ):
        async with self.uow:
            r = self.uow.credit_scenario
            if await r.scenario_exists_by_key(body.macro_scenario_key):
                raise HTTPException(
                    400,
                    f"Scenario with key '{body.macro_scenario_key}' already exists",
                )
            sc = CreditPortfolioScenario(
                **body.model_dump(),
                created_by_user_id=actor_id, updated_by_user_id=actor_id,
            )
            r.add(sc)
            await r.flush()
            await r.refresh(sc)
            return sc

    async def update_scenario(
        self, scenario_id: UUID,
        body: CreditPortfolioScenarioUpdate, *, actor_id: UUID,
    ):
        async with self.uow:
            r = self.uow.credit_scenario
            sc = await r.get_scenario(scenario_id)
            if not sc:
                raise HTTPException(404, "Scenario not found")
            for k, v in body.model_dump(exclude_unset=True).items():
                setattr(sc, k, v)
            sc.updated_by_user_id = actor_id
            await r.flush()
            await r.refresh(sc)
            return sc

    async def delete_scenario(self, scenario_id: UUID) -> None:
        async with self.uow:
            r = self.uow.credit_scenario
            sc = await r.get_scenario(scenario_id)
            if not sc:
                raise HTTPException(404, "Scenario not found")
            await r.delete(sc)
            await r.flush()

    # ─── per-loan overrides ───────────────────────────────────────

    async def list_overrides(self, scenario_id: UUID):
        async with self.uow:
            return await self.uow.credit_scenario.list_overrides(scenario_id)

    async def upsert_override(
        self, scenario_id: UUID, loan_id: UUID, body: LoanScenarioUpdate,
    ):
        async with self.uow:
            r = self.uow.credit_scenario
            ov = await r.get_override(scenario_id, loan_id)
            if ov is None:
                ov = CreditPortfolioLoanScenario(
                    scenario_id=scenario_id, loan_id=loan_id,
                    **body.model_dump(exclude_unset=True),
                )
                r.add(ov)
            else:
                for k, v in body.model_dump(exclude_unset=True).items():
                    setattr(ov, k, v)
            await r.flush()
            await r.refresh(ov)
            return ov

    async def delete_override(self, scenario_id: UUID, loan_id: UUID) -> None:
        async with self.uow:
            r = self.uow.credit_scenario
            ov = await r.get_override(scenario_id, loan_id)
            if ov is None:
                raise HTTPException(404, "Override not found")
            await r.delete(ov)
            await r.flush()

    # ─── custom indicators ────────────────────────────────────────

    async def list_custom_indicators(self):
        async with self.uow:
            return await self.uow.credit_scenario.list_custom_indicators()

    async def create_custom_indicator(
        self, body: CustomIndicatorCreate, *, actor_id: UUID,
    ):
        if body.input_type not in CUSTOM_INDICATOR_INPUT_TYPES:
            raise HTTPException(
                400,
                f"input_type must be one of: {', '.join(CUSTOM_INDICATOR_INPUT_TYPES)}",
            )
        if (
            body.aggregation is not None
            and body.aggregation not in CUSTOM_INDICATOR_AGGREGATIONS
        ):
            raise HTTPException(
                400,
                f"aggregation must be one of: {', '.join(CUSTOM_INDICATOR_AGGREGATIONS)}",
            )
        async with self.uow:
            r = self.uow.credit_scenario
            if await r.indicator_exists_by_key(body.key):
                raise HTTPException(400, f"Indicator with key '{body.key}' already exists")
            ind = CreditCustomIndicator(
                **body.model_dump(),
                created_by_user_id=actor_id,
                updated_by_user_id=actor_id,
            )
            r.add(ind)
            await r.flush()
            await r.refresh(ind)
            return ind

    async def update_custom_indicator(
        self, ind_id: UUID, body: CustomIndicatorUpdate, *, actor_id: UUID,
    ):
        async with self.uow:
            r = self.uow.credit_scenario
            ind = await r.get_custom_indicator(ind_id)
            if not ind:
                raise HTTPException(404, "Indicator not found")
            data = body.model_dump(exclude_unset=True)
            if "input_type" in data and data["input_type"] not in CUSTOM_INDICATOR_INPUT_TYPES:
                raise HTTPException(
                    400,
                    f"input_type must be one of: {', '.join(CUSTOM_INDICATOR_INPUT_TYPES)}",
                )
            if (
                "aggregation" in data and data["aggregation"] is not None
                and data["aggregation"] not in CUSTOM_INDICATOR_AGGREGATIONS
            ):
                raise HTTPException(
                    400,
                    f"aggregation must be one of: {', '.join(CUSTOM_INDICATOR_AGGREGATIONS)}",
                )
            for k, v in data.items():
                setattr(ind, k, v)
            ind.updated_by_user_id = actor_id
            await r.flush()
            await r.refresh(ind)
            return ind

    async def delete_custom_indicator(self, ind_id: UUID) -> None:
        async with self.uow:
            r = self.uow.credit_scenario
            ind = await r.get_custom_indicator(ind_id)
            if not ind:
                raise HTTPException(404, "Indicator not found")
            await r.delete(ind)
            await r.flush()

    # ─── formula test (delegates to evaluator) ────────────────────

    async def formula_test(self, formula_text: str, *, loan_id: Optional[UUID]):
        from app.services.risk_formula_evaluator import evaluate_formula

        async with self.uow:
            r = self.uow.credit_scenario
            loan = (
                await r.get_loan(loan_id) if loan_id
                else await r.get_first_active_loan()
            )

        if loan is None:
            return FormulaTestResponse(ok=False, error="Нет ни одного кредита для теста")

        today = _date.today()
        days_to_maturity = (loan.date_due - today).days if loan.date_due else 9999
        ns = {
            "debt_usd": float(loan.debt_usd or 0),
            "sum_total": float(loan.sum_total or 0),
            "sum_disbursed": float(loan.sum_disbursed or 0),
            "rate": float(loan.rate or 0),
            "is_guaranteed": bool(loan.is_guaranteed),
            "lender_type": loan.lender_type or "",
            "currency": loan.currency or "",
            "overdue_days": 0,
            "days_to_maturity": days_to_maturity,
            "repayments_remaining": float(loan.debt_usd or 0),
            "loan": {"default_probability": None, "forgiveness_pct": None},
            "scenario": {"default_rate_pct": 0.02, "state_forgiveness_pct": 0.0},
            "company": {}, "custom": {},
        }
        ok, err, val = evaluate_formula(formula_text, ns)
        steps = [
            f"debt_usd = {ns['debt_usd']}",
            f"lender_type = {ns['lender_type']}, is_guaranteed = {ns['is_guaranteed']}",
            f"days_to_maturity = {ns['days_to_maturity']}",
            f"scenario.default_rate_pct = {ns['scenario']['default_rate_pct']}",
        ]
        if ok:
            steps.append(f"=> EL = {val}")
        return FormulaTestResponse(
            ok=ok, error=err, loan_code=loan.loan_code,
            inputs=ns, steps=steps, final_value=val,
        )

    # ─── overview (Pack 7.41) ─────────────────────────────────────

    async def overview(self, *, cp_scenario_id: Optional[UUID], user) -> dict:
        """Executive dashboard overview — composes _aggregate_impl + extras."""
        # Self-heal migrations
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            try:
                from app.core.runtime_migrations_p741 import pack_741_self_heal
                await pack_741_self_heal(session)
            except Exception:
                pass

        # Authoritative aggregate from credit-portfolio source-of-truth
        from app.api.routes.credit_portfolio import _aggregate_impl
        async with self.uow:
            session = self.uow._session  # type: ignore[attr-defined]
            aggr = await _aggregate_impl(
                company_id=None, company_code=None, as_of=None,
                db=session, user=user,
            )
            loans = await self.uow.credit_scenario.list_active_loans()

        today = _date.today()
        by_maturity = defaultdict(lambda: {"debt": 0.0, "count": 0})
        overdue_companies = set()
        due_12mo_loans = 0

        for ln in loans:
            debt = float(ln.debt_usd or 0)
            if ln.date_due:
                dtm = (ln.date_due - today).days
                if ln.date_due < today and debt > 0:
                    bucket = "overdue"
                    if ln.company_id:
                        overdue_companies.add(ln.company_id)
                elif dtm < 365:
                    bucket = "lt_1y"
                    due_12mo_loans += 1
                elif dtm < 365 * 3:
                    bucket = "1_3y"
                elif dtm < 365 * 5:
                    bucket = "3_5y"
                else:
                    bucket = "gt_5y"
            else:
                bucket = "gt_5y"
            by_maturity[bucket]["debt"] += debt
            by_maturity[bucket]["count"] += 1

        outstanding = float(aggr.total_usd or 0)

        maturity_list = []
        for k, v in by_maturity.items():
            pct = (v["debt"] / outstanding * 100) if outstanding > 0 else 0
            maturity_list.append({
                "bucket": k, "label_ru": MATURITY_LABELS.get(k, k),
                "debt_usd": v["debt"], "loans_count": v["count"], "pct": pct,
            })
        maturity_list.sort(key=lambda x: x["debt_usd"], reverse=True)

        by_lender = [
            {
                "lender_type": x.lender_type,
                "label_ru": LENDER_LABELS_RU.get(x.lender_type, x.label),
                "label": x.label, "color": x.color,
                "debt_usd": float(x.debt_usd or 0),
                "loans_count": int(x.loans_count or 0),
                "pct": float(x.pct_of_total or 0) * 100,
            }
            for x in aggr.by_lender_type
        ]
        by_currency = [
            {
                "currency": x.currency,
                "label_ru": CURRENCY_LABELS_RU.get(x.currency, x.currency),
                "debt_usd": float(x.debt_usd or 0),
                "debt_currency": float(x.debt_currency or 0),
                "loans_count": int(x.loans_count or 0),
                "pct": float(x.pct_of_total or 0) * 100,
                "avg_rate": float(x.avg_rate or 0) if x.avg_rate else None,
            }
            for x in aggr.by_currency
        ]

        non_uzs = sum(
            float(x.debt_usd or 0) for x in aggr.by_currency if x.currency != "UZS"
        )
        fx_exposure_pct = (non_uzs / outstanding * 100) if outstanding > 0 else 0

        # Expected Loss
        el_total = 0.0
        el_loans = 0
        for ln in loans:
            debt = float(ln.debt_usd or 0)
            if debt <= 0:
                continue
            rr = DEFAULT_RR_BY_LENDER.get(ln.lender_type, 0.5)
            if ln.is_guaranteed:
                rr = min(0.85, rr + 0.30)
            pd = DEFAULT_PD_BY_LENDER.get(ln.lender_type, 0.025)
            if ln.date_due and ln.date_due < today:
                pd = min(1.0, pd * 5)
            contribution = debt * pd * (1 - rr)
            el_total += contribution
            if contribution > 1000:
                el_loans += 1

        return {
            "portfolio_total_usd": float(aggr.loaned_total_usd or 0),
            "outstanding_usd": outstanding,
            "repaid_usd": float(aggr.repaid_total_usd or 0),
            "repaid_pct": float(aggr.repaid_pct or 0) * 100,
            "loans_count": int(aggr.loans_count or 0),
            "banks_count": int(aggr.banks_count or 0),
            "companies_count": len({
                ln.company_id for ln in loans
                if ln.company_id and (ln.debt_usd or 0) > 0
            }),
            "soes_count": 22,
            "avg_rate_weighted": float(aggr.avg_rate or 0) * 100,
            "guaranteed_usd": float(aggr.guaranteed_amount or 0),
            "guaranteed_pct": (
                float(aggr.guaranteed_amount or 0) / outstanding * 100
            ) if outstanding > 0 else 0,
            "due_12mo_usd": float(aggr.payment_this_year or 0)
                            + float(aggr.payment_next_year or 0),
            "due_12mo_loans": due_12mo_loans,
            "overdue_usd": float(aggr.overdue_amount or 0),
            "overdue_loans": sum(
                1 for ln in loans
                if ln.date_due and ln.date_due < today and (ln.debt_usd or 0) > 0
            ),
            "overdue_companies": len(overdue_companies),
            "fx_exposure_usd": non_uzs,
            "fx_exposure_pct": fx_exposure_pct,
            "expected_loss_usd": el_total,
            "expected_loss_loans": el_loans,
            "by_lender_type": by_lender,
            "by_currency": by_currency,
            "by_maturity": maturity_list,
            "as_of_date": str(aggr.as_of_date),
        }

    # ─── drilldown loans ──────────────────────────────────────────

    async def drilldown_loans(
        self, *,
        lender_type: Optional[str], currency: Optional[str],
        maturity_bucket: Optional[str], is_guaranteed: Optional[bool],
        overdue_only: bool, limit: int,
    ) -> list[dict]:
        from app.models.credit import CreditPortfolioLoan
        today = _date.today()
        filters = [CreditPortfolioLoan.deleted_at.is_(None)]
        if lender_type:
            filters.append(CreditPortfolioLoan.lender_type == lender_type)
        if currency:
            if currency == "OTHER":
                filters.append(~CreditPortfolioLoan.currency.in_(KNOWN_CURRENCIES))
            else:
                filters.append(CreditPortfolioLoan.currency == currency)
        if is_guaranteed is not None:
            filters.append(CreditPortfolioLoan.is_guaranteed == is_guaranteed)

        async with self.uow:
            rows = await self.uow.credit_scenario.list_loans_with_company_filtered(
                filters=filters,
            )

        out = []
        for ln, co_name in rows:
            debt = float(ln.debt_usd or 0)
            dtm = (ln.date_due - today).days if ln.date_due else 99999
            od = (today - ln.date_due).days if (
                ln.date_due and ln.date_due < today and debt > 0
            ) else 0
            bucket = (
                "overdue" if od > 0
                else "lt_1y" if dtm < 365
                else "1_3y" if dtm < 365 * 3
                else "3_5y" if dtm < 365 * 5
                else "gt_5y"
            )
            if maturity_bucket and bucket != maturity_bucket:
                continue
            if overdue_only and od == 0:
                continue
            out.append({
                "loan_id": str(ln.id), "loan_code": ln.loan_code,
                "bank": ln.bank, "bank_short_name": ln.bank_short_name,
                "company_name": co_name or "—",
                "borrower_unit": ln.borrower_unit,
                "lender_type": ln.lender_type, "currency": ln.currency,
                "rate": float(ln.rate) if ln.rate else None,
                "rate_text": ln.rate_text,
                "sum_total": float(ln.sum_total) if ln.sum_total else None,
                "debt_currency": float(ln.debt_currency) if ln.debt_currency else None,
                "debt_usd": debt or None,
                "date_get": ln.date_get.isoformat() if ln.date_get else None,
                "date_due": ln.date_due.isoformat() if ln.date_due else None,
                "is_guaranteed": bool(ln.is_guaranteed),
                "days_to_maturity": dtm,
                "overdue_days": od,
            })
        out.sort(key=lambda r: r["debt_usd"] or 0, reverse=True)
        return out[:limit]

    async def drilldown_by_company(
        self, *,
        lender_type: Optional[str], currency: Optional[str],
        maturity_bucket: Optional[str], top_n: int,
    ) -> list[dict]:
        loans = await self.drilldown_loans(
            lender_type=lender_type, currency=currency,
            maturity_bucket=maturity_bucket, is_guaranteed=None,
            overdue_only=False, limit=10000,
        )
        by_co = {}
        total = 0.0
        for ln in loans:
            name = ln["company_name"]
            d = ln["debt_usd"] or 0
            total += d
            if name not in by_co:
                by_co[name] = {
                    "label_ru": name, "debt_usd": 0.0,
                    "loans_count": 0, "banks": set(),
                }
            by_co[name]["debt_usd"] += d
            by_co[name]["loans_count"] += 1
            by_co[name]["banks"].add(ln["bank_short_name"] or ln["bank"])
        rows = [{
            "key": n, "label_ru": n, "debt_usd": g["debt_usd"],
            "pct": (g["debt_usd"] / total * 100) if total > 0 else 0,
            "loans_count": g["loans_count"], "banks_count": len(g["banks"]),
        } for n, g in by_co.items()]
        rows.sort(key=lambda r: r["debt_usd"], reverse=True)
        return rows[:top_n]

    async def drilldown_by_bank(
        self, *,
        lender_type: Optional[str], currency: Optional[str],
        maturity_bucket: Optional[str], top_n: int,
    ) -> list[dict]:
        loans = await self.drilldown_loans(
            lender_type=lender_type, currency=currency,
            maturity_bucket=maturity_bucket, is_guaranteed=None,
            overdue_only=False, limit=10000,
        )
        by_b = {}
        total = 0.0
        for ln in loans:
            name = ln["bank"]
            d = ln["debt_usd"] or 0
            total += d
            if name not in by_b:
                by_b[name] = {
                    "label_ru": name, "debt_usd": 0.0,
                    "loans_count": 0, "lender_type": ln["lender_type"],
                }
            by_b[name]["debt_usd"] += d
            by_b[name]["loans_count"] += 1
        rows = [{
            "key": n, "label_ru": n, "debt_usd": g["debt_usd"],
            "pct": (g["debt_usd"] / total * 100) if total > 0 else 0,
            "loans_count": g["loans_count"], "lender_type": g["lender_type"],
        } for n, g in by_b.items()]
        rows.sort(key=lambda r: r["debt_usd"], reverse=True)
        return rows[:top_n]
