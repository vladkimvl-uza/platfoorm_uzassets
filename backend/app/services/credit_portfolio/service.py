"""Credit Portfolio use-cases. Routes are thin HTTP shims; all business logic
(loan CRUD, aggregations, risk metrics, payment recompute, EBITDA resolution)
lives here.

MissingGreenlet fix (the design guide §4.2): all `_to_read(loan)` paths after a
`session.refresh(loan)` now pass `company=` explicitly. The repository's
`get_loan(with_company=True)` and `list_loans_filtered(with_company=True)`
calls eager-load via `selectinload`, so the `_to_read` helper only ever sees
materialised state — no lazy property access remains.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from fastapi import status as http_status

from app.core.access import allowed_company_ids
from app.core.security import has_effective_permission
from app.models.company import Company
from app.models.credit import (
    CreditPortfolioLoan,
    CreditPortfolioPayment,
)
from app.models.user import User
from app.schemas.credit_portfolio import (
    BankBreakdown,
    BankRow,
    BulkImportRequest,
    BulkImportResponse,
    CompaniesWithLoansResponse,
    CompanyAggregateRow,
    CompanyPaymentByYear,
    CompanyWithLoansRow,
    CreditPortfolioAggregate,
    CurrencyBreakdown,
    FxRateRead,
    FxRateUpsert,
    LenderTypeBreakdown,
    LoanCreate,
    LoanPaymentsSummary,
    LoanRead,
    LoanUpdate,
    MaturityBucket,
    PaymentCreate,
    PaymentRead,
    PaymentUpdate,
    RateMatrixCell,
    RiskBubblePoint,
    RiskMetrics,
    SankeyFlow,
    TopLoanRef,
    YearBucket,
)
from app.services.credit_portfolio_helpers import (
    LENDER_TYPE_META,
    bank_short_name,
    classify_lender,
    days_between,
    maturity_bucket,
    year_of,
)
from app.uow.ports import UnitOfWorkABC

_DEFAULT_AS_OF = date_type(2026, 1, 1)
_DEFAULT_USD_RATE = Decimal("12078.47")

_FALLBACK_SECTOR_COLORS = {
    "mining": "#9B8EC4",
    "metallurgy": "#9B8EC4",
    "oil_gas": "#0A7B5E",
    "energy": "#EF9F27",
    "transport": "#378ADD",
    "telecom": "#378ADD",
    "chemistry": "#888780",
    "other": "#888780",
}


@dataclass
class CreditPortfolioService:
    uow: UnitOfWorkABC

    # ─── Common gates (must be called inside `async with self.uow`) ──

    async def _require(self, user: User, perm: str) -> None:
        if not await has_effective_permission(self.uow._session, user, perm):  # type: ignore[attr-defined]
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, f"{perm} required")

    async def _scope_ids(self, user: User) -> Optional[set[UUID]]:
        return await allowed_company_ids(self.uow._session, user)  # type: ignore[attr-defined]

    async def _check_company_access(
        self, user: User, company_id: Optional[UUID]
    ) -> None:
        if company_id is None:
            return
        scope = await self._scope_ids(user)
        if scope is not None and company_id not in scope:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "No access")

    @staticmethod
    def _to_read(
        loan: CreditPortfolioLoan, company: Optional[Company] = None
    ) -> LoanRead:
        """Materialised-only — no lazy attr access. Always pass `company`
        explicitly after `refresh()`."""
        payload = LoanRead.model_validate(loan)
        if company is not None:
            payload.company_name_ru = company.name_ru or company.name_en or company.code
        elif loan.company is not None:
            payload.company_name_ru = (
                loan.company.name_ru or loan.company.name_en or loan.company.code
            )
        return payload

    # ─── Loans CRUD ───────────────────────────────────────────────

    async def list_loans(
        self,
        user: User,
        *,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        currency: Optional[str] = None,
        lender_type: Optional[str] = None,
        search: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[LoanRead]:
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio
            if company_code:
                co = await repo.get_company_by_code(company_code)
                if co is None:
                    return []
                company_id = co.id
            scope = await self._scope_ids(user)
            loans = await repo.list_loans_filtered(
                company_id=company_id,
                currency=currency,
                lender_type=lender_type,
                search=search,
                include_deleted=include_deleted,
                allowed_company_ids=scope,
            )
            return [self._to_read(r) for r in loans]

    async def get_loan(self, loan_id: UUID, user: User) -> LoanRead:
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio
            loan = await repo.get_loan(loan_id, with_company=True)
            if loan is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")
            await self._check_company_access(user, loan.company_id)
            return self._to_read(loan)

    async def create_loan(self, payload: LoanCreate, user: User) -> LoanRead:
        async with self.uow:
            await self._require(user, "credit.edit")
            await self._check_company_access(user, payload.company_id)
            repo = self.uow.credit_portfolio
            if await repo.get_loan_by_code(payload.loan_code) is not None:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    f"Loan code '{payload.loan_code}' already exists",
                )

            auto_flags = dict(payload.auto_flags)
            lender_type = payload.lender_type
            if lender_type is None:
                lender_type = classify_lender(payload.bank)
                auto_flags["lenderType"] = True

            loan = CreditPortfolioLoan(
                loan_code=payload.loan_code,
                company_id=payload.company_id,
                borrower_unit=payload.borrower_unit,
                bank=payload.bank,
                bank_short_name=payload.bank_short_name or bank_short_name(payload.bank),
                contract_ref=payload.contract_ref,
                currency=payload.currency.upper(),
                rate=payload.rate,
                rate_text=payload.rate_text,
                sum_total=payload.sum_total,
                sum_disbursed=payload.sum_disbursed,
                debt_currency=payload.debt_currency,
                debt_usd=payload.debt_usd,
                date_get=payload.date_get,
                date_due=payload.date_due,
                is_guaranteed=payload.is_guaranteed,
                lender_type=lender_type,
                auto_flags=auto_flags,
                notes=payload.notes,
                as_of_date=payload.as_of_date,
                created_by_user_id=user.id,
            )
            repo.add(loan)
            await repo.flush()
            await repo.refresh(loan)
            company = (
                await repo.get_company_by_id(loan.company_id)
                if loan.company_id else None
            )
            return self._to_read(loan, company=company)

    async def update_loan(
        self, loan_id: UUID, payload: LoanUpdate, user: User
    ) -> LoanRead:
        async with self.uow:
            await self._require(user, "credit.edit")
            repo = self.uow.credit_portfolio
            loan = await repo.get_loan(loan_id)
            if loan is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")
            await self._check_company_access(user, loan.company_id)

            data = payload.model_dump(exclude_unset=True)
            for k, v in data.items():
                setattr(loan, k, v)
            if data.get("bank") and not data.get("bank_short_name"):
                loan.bank_short_name = bank_short_name(loan.bank)
            if data.get("currency"):
                loan.currency = loan.currency.upper()
            loan.updated_by_user_id = user.id

            await repo.flush()
            await repo.refresh(loan)
            company = (
                await repo.get_company_by_id(loan.company_id)
                if loan.company_id else None
            )
            return self._to_read(loan, company=company)

    async def delete_loan(self, loan_id: UUID, user: User) -> None:
        async with self.uow:
            await self._require(user, "credit.delete")
            repo = self.uow.credit_portfolio
            loan = await repo.get_loan(loan_id)
            if loan is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")
            await self._check_company_access(user, loan.company_id)
            loan.deleted_at = date_type.today()
            loan.updated_by_user_id = user.id

    async def bulk_import(
        self, payload: BulkImportRequest, user: User
    ) -> BulkImportResponse:
        async with self.uow:
            await self._require(user, "credit.edit")
            repo = self.uow.credit_portfolio
            scope = await self._scope_ids(user)
            inserted = updated = skipped = 0
            errors: list[str] = []

            co_by_id: dict[UUID, Company] = {}
            co_by_code: dict[str, Company] = {}
            co_by_name: dict[str, Company] = {}
            for co in await repo.list_all_companies():
                co_by_id[co.id] = co
                if co.code:
                    co_by_code[co.code.lower()] = co
                if co.name_ru:
                    co_by_name[co.name_ru.strip().lower()] = co

            for item in payload.items:
                co: Optional[Company] = None
                if item.company_id:
                    co = co_by_id.get(item.company_id)
                elif item.company_code:
                    co = co_by_code.get(item.company_code.lower())
                elif item.company_name_ru:
                    co = co_by_name.get(item.company_name_ru.strip().lower())

                if co is None:
                    errors.append(
                        f"loan {item.loan_code}: company not resolved "
                        f"(id={item.company_id}, code={item.company_code}, name={item.company_name_ru})"
                    )
                    skipped += 1
                    continue
                if scope is not None and co.id not in scope:
                    errors.append(f"loan {item.loan_code}: no access to company {co.code}")
                    skipped += 1
                    continue

                existing = await repo.get_loan_by_code(item.loan_code)
                lender_type = item.lender_type or classify_lender(item.bank)
                auto_flags = dict(item.auto_flags or {})
                if not item.lender_type:
                    auto_flags["lenderType"] = True

                if existing is not None:
                    if not payload.overwrite_existing:
                        skipped += 1
                        continue
                    existing.company_id = co.id
                    existing.borrower_unit = item.borrower_unit
                    existing.bank = item.bank
                    existing.bank_short_name = item.bank_short_name or bank_short_name(item.bank)
                    existing.contract_ref = item.contract_ref
                    existing.currency = item.currency.upper()
                    existing.rate = item.rate
                    existing.rate_text = item.rate_text
                    existing.sum_total = item.sum_total
                    existing.sum_disbursed = item.sum_disbursed
                    existing.debt_currency = item.debt_currency
                    existing.debt_usd = item.debt_usd
                    existing.date_get = item.date_get
                    existing.date_due = item.date_due
                    existing.is_guaranteed = item.is_guaranteed
                    existing.lender_type = lender_type
                    existing.auto_flags = auto_flags
                    existing.notes = item.notes
                    existing.as_of_date = item.as_of_date
                    existing.updated_by_user_id = user.id
                    updated += 1
                else:
                    repo.add(CreditPortfolioLoan(
                        loan_code=item.loan_code,
                        company_id=co.id,
                        borrower_unit=item.borrower_unit,
                        bank=item.bank,
                        bank_short_name=item.bank_short_name or bank_short_name(item.bank),
                        contract_ref=item.contract_ref,
                        currency=item.currency.upper(),
                        rate=item.rate,
                        rate_text=item.rate_text,
                        sum_total=item.sum_total,
                        sum_disbursed=item.sum_disbursed,
                        debt_currency=item.debt_currency,
                        debt_usd=item.debt_usd,
                        date_get=item.date_get,
                        date_due=item.date_due,
                        is_guaranteed=item.is_guaranteed,
                        lender_type=lender_type,
                        auto_flags=auto_flags,
                        notes=item.notes,
                        as_of_date=item.as_of_date,
                        created_by_user_id=user.id,
                    ))
                    inserted += 1

            return BulkImportResponse(
                inserted=inserted, updated=updated, skipped=skipped, errors=errors
            )

    # ─── Sidebar / League table ───────────────────────────────────

    async def companies_with_loans(self, user: User) -> CompaniesWithLoansResponse:
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio
            scope = await self._scope_ids(user)
            rows = await repo.list_companies_with_loans(allowed_company_ids=scope)

        items = [
            CompanyWithLoansRow(
                company_id=r.id,
                company_name_ru=r.name_ru or r.code,
                company_code=r.code,
                sector=r.sector_code,
                sector_color=r.sector_color or _FALLBACK_SECTOR_COLORS.get(
                    r.sector_code or "", "#888780"
                ),
                loans_count=int(r.cnt),
                debt_usd=Decimal(str(r.debt or 0)),
            )
            for r in rows
        ]
        return CompaniesWithLoansResponse(
            items=items,
            total_loans=sum(i.loans_count for i in items),
            total_debt_usd=sum((i.debt_usd for i in items), Decimal("0")),
        )

    # ─── Aggregate dashboard ──────────────────────────────────────

    async def aggregate(
        self,
        user: User,
        *,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        as_of: Optional[date_type] = None,
    ) -> CreditPortfolioAggregate:
        as_of = as_of or _DEFAULT_AS_OF
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio

            if company_code:
                co = await repo.get_company_by_code(company_code)
                if co is None:
                    raise HTTPException(
                        http_status.HTTP_404_NOT_FOUND, "Company not found"
                    )
                company_id = co.id

            scope = await self._scope_ids(user)
            loans = await repo.list_active_loans(
                company_id=company_id,
                with_company=True,
                allowed_company_ids=scope,
            )

            if not loans:
                return self._empty_aggregate(as_of)

            fx = await self._resolve_fx(repo, as_of)
            return self._build_aggregate(loans, as_of, fx)

    @staticmethod
    def _empty_aggregate(as_of: date_type) -> CreditPortfolioAggregate:
        return CreditPortfolioAggregate(
            as_of_date=as_of,
            total_usd=Decimal("0"),
            total_local={},
            loans_count=0,
            banks_count=0,
            avg_rate=Decimal("0"),
            loaned_total_usd=Decimal("0"),
            repaid_total_usd=Decimal("0"),
            repaid_pct=0.0,
            by_currency=[],
            by_lender_type=[],
            by_bank_top10=[],
            by_bank_full=[],
            by_year=[],
            by_bucket=[],
            rate_matrix=[],
            guaranteed_amount=Decimal("0"),
            unguaranteed_amount=Decimal("0"),
            payment_this_year=Decimal("0"),
            payment_next_year=Decimal("0"),
            overdue_amount=Decimal("0"),
            top_payment_loan=None,
            nearest_payment_loan=None,
            avg_rate_by_currency={},
        )

    async def _resolve_fx(self, repo, as_of: date_type) -> dict[str, Decimal]:
        fx_rows = await repo.fx_rates_for(as_of)
        if not fx_rows:
            latest_date = await repo.latest_fx_date()
            if latest_date:
                fx_rows = await repo.fx_rates_for(latest_date)
        fx: dict[str, Decimal] = {
            f.currency: Decimal(str(f.rate_to_uzs)) for f in fx_rows
        }
        fx.setdefault("USD", _DEFAULT_USD_RATE)
        fx.setdefault("UZS", Decimal("1.0"))
        return fx

    def _build_aggregate(
        self,
        loans: Sequence[CreditPortfolioLoan],
        as_of: date_type,
        fx: dict[str, Decimal],
    ) -> CreditPortfolioAggregate:
        total_usd = Decimal("0")
        total_local: dict[str, Decimal] = {}
        weighted_rate = Decimal("0")
        rate_base = Decimal("0")
        by_currency: dict[str, dict] = {}
        by_bank: dict[str, dict] = {}
        by_year: dict[int, dict] = {}
        by_bucket: dict[str, dict] = {}
        by_lender: dict[str, dict] = {}
        rate_matrix: dict[tuple[str, str], dict] = {}
        guaranteed = Decimal("0")
        unguaranteed = Decimal("0")
        loaned_total = Decimal("0")
        repaid_total = Decimal("0")
        nearest_payment: Optional[CreditPortfolioLoan] = None
        top_payment_candidate: Optional[CreditPortfolioLoan] = None
        cur_year = as_of.year

        for ln in loans:
            debt_usd = Decimal(ln.debt_usd or 0)
            debt_cur = Decimal(ln.debt_currency or 0)
            currency = ln.currency
            rate = ln.rate
            bk = ln.bank_short_name or bank_short_name(ln.bank)
            lender_t = ln.lender_type or classify_lender(ln.bank)

            total_usd += debt_usd
            total_local[currency] = total_local.get(currency, Decimal("0")) + debt_cur

            sum_total = Decimal(ln.sum_total or 0)
            if debt_cur > 0 and debt_usd > 0:
                sum_total_usd = sum_total * (debt_usd / debt_cur)
            else:
                fx_cur = fx.get(currency, Decimal("1"))
                fx_usd = fx.get("USD", _DEFAULT_USD_RATE)
                sum_total_usd = (sum_total * fx_cur / fx_usd) if fx_usd else Decimal("0")
            if sum_total_usd == 0 and debt_usd > 0:
                sum_total_usd = debt_usd
            loaned_total += sum_total_usd
            repaid_total += max(Decimal("0"), sum_total_usd - debt_usd)

            if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
                weighted_rate += Decimal(rate) * debt_usd
                rate_base += debt_usd

            c = by_currency.setdefault(
                currency,
                {"debt_usd": Decimal("0"), "debt_cur": Decimal("0"), "count": 0,
                 "rate_w": Decimal("0"), "rate_d": Decimal("0")},
            )
            c["debt_usd"] += debt_usd
            c["debt_cur"] += debt_cur
            c["count"] += 1
            if rate is not None and 0 < float(rate) < 1:
                c["rate_w"] += Decimal(rate) * debt_usd
                c["rate_d"] += debt_usd

            b = by_bank.setdefault(
                bk,
                {"debt_usd": Decimal("0"), "count": 0,
                 "full_name": ln.bank, "lender_type": lender_t},
            )
            b["debt_usd"] += debt_usd
            b["count"] += 1
            if not b.get("lender_type"):
                b["lender_type"] = lender_t

            yr = year_of(ln.date_due)
            if yr is not None:
                ye = by_year.setdefault(yr, {"debt_usd": Decimal("0"), "count": 0})
                ye["debt_usd"] += debt_usd
                ye["count"] += 1
            bu = maturity_bucket(ln.date_due, as_of)
            bo = by_bucket.setdefault(bu, {"debt_usd": Decimal("0"), "count": 0})
            bo["debt_usd"] += debt_usd
            bo["count"] += 1

            lt_e = by_lender.setdefault(
                lender_t, {"debt_usd": Decimal("0"), "count": 0}
            )
            lt_e["debt_usd"] += debt_usd
            lt_e["count"] += 1

            if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
                mtx_e = rate_matrix.setdefault(
                    (lender_t, currency),
                    {"w": Decimal("0"), "d": Decimal("0"), "count": 0},
                )
                mtx_e["w"] += Decimal(rate) * debt_usd
                mtx_e["d"] += debt_usd
                mtx_e["count"] += 1

            if ln.is_guaranteed:
                guaranteed += debt_usd
            else:
                unguaranteed += debt_usd

            if ln.date_due is not None:
                d = days_between(as_of, ln.date_due)
                if d is not None and 0 <= d <= 365:
                    if (top_payment_candidate is None
                        or debt_usd > Decimal(top_payment_candidate.debt_usd or 0)):
                        top_payment_candidate = ln
                    if (nearest_payment is None
                        or (ln.date_due < nearest_payment.date_due)):
                        nearest_payment = ln

        avg_rate = (weighted_rate / rate_base) if rate_base else Decimal("0")

        by_currency_list = [
            CurrencyBreakdown(
                currency=cur,
                debt_usd=e["debt_usd"],
                debt_currency=e["debt_cur"],
                pct_of_total=float(e["debt_usd"] / total_usd) if total_usd else 0.0,
                avg_rate=(e["rate_w"] / e["rate_d"]) if e["rate_d"] else None,
                loans_count=e["count"],
            )
            for cur, e in sorted(by_currency.items(), key=lambda x: -x[1]["debt_usd"])
        ]

        by_lender_list = []
        for lt in ("bond", "foreign", "local", "state"):
            if lt not in by_lender:
                continue
            meta = LENDER_TYPE_META[lt]
            e = by_lender[lt]
            by_lender_list.append(LenderTypeBreakdown(
                lender_type=lt,
                label=meta["label"],
                color=meta["color"],
                debt_usd=e["debt_usd"],
                pct_of_total=float(e["debt_usd"] / total_usd) if total_usd else 0.0,
                loans_count=e["count"],
            ))
        by_lender_list.sort(key=lambda x: -x.debt_usd)

        by_bank_top10 = sorted(
            [
                BankBreakdown(
                    bank_short_name=k,
                    debt_usd=v["debt_usd"],
                    pct_of_total=float(v["debt_usd"] / total_usd) if total_usd else 0.0,
                    loans_count=v["count"],
                )
                for k, v in by_bank.items()
            ],
            key=lambda x: -x.debt_usd,
        )[:10]

        by_bank_full = sorted(
            [
                BankRow(
                    bank=v["full_name"],
                    bank_short_name=k,
                    lender_type=v.get("lender_type"),
                    debt_usd=v["debt_usd"],
                    loans_count=v["count"],
                    pct_of_total=float(v["debt_usd"] / total_usd) if total_usd else 0.0,
                )
                for k, v in by_bank.items()
            ],
            key=lambda x: -x.debt_usd,
        )

        rate_matrix_list = [
            RateMatrixCell(
                lender_type=lt,
                currency=cur,
                rate=(e["w"] / e["d"]) if e["d"] else Decimal("0"),
                debt_usd=e["d"],
                loans_count=e["count"],
            )
            for (lt, cur), e in rate_matrix.items()
            if e["d"] > 0
        ]
        rate_matrix_list.sort(key=lambda x: (x.lender_type, -x.debt_usd))

        by_year_list = sorted(
            [
                YearBucket(year=y, debt_usd=v["debt_usd"], loans_count=v["count"])
                for y, v in by_year.items()
                if y >= as_of.year
            ],
            key=lambda x: x.year,
        )

        bucket_order = ("overdue", "<1 года", "1–3 года", "3–5 лет", ">5 лет", "unknown")
        by_bucket_list = [
            MaturityBucket(
                bucket=b,
                debt_usd=by_bucket[b]["debt_usd"],
                loans_count=by_bucket[b]["count"],
            )
            for b in bucket_order
            if b in by_bucket
        ]

        return CreditPortfolioAggregate(
            as_of_date=as_of,
            total_usd=total_usd,
            total_local=total_local,
            loans_count=len(loans),
            banks_count=len(by_bank),
            avg_rate=avg_rate,
            loaned_total_usd=loaned_total,
            repaid_total_usd=repaid_total,
            repaid_pct=float(repaid_total / loaned_total) if loaned_total > 0 else 0.0,
            by_currency=by_currency_list,
            by_lender_type=by_lender_list,
            by_bank_top10=by_bank_top10,
            by_bank_full=by_bank_full,
            by_year=by_year_list,
            by_bucket=by_bucket_list,
            rate_matrix=rate_matrix_list,
            guaranteed_amount=guaranteed,
            unguaranteed_amount=unguaranteed,
            payment_this_year=Decimal(str(by_year.get(cur_year, {"debt_usd": 0})["debt_usd"])),
            payment_next_year=Decimal(str(by_year.get(cur_year + 1, {"debt_usd": 0})["debt_usd"])),
            overdue_amount=Decimal(str(by_bucket.get("overdue", {"debt_usd": 0})["debt_usd"])),
            top_payment_loan=self._to_topref(top_payment_candidate, as_of),
            nearest_payment_loan=self._to_topref(nearest_payment, as_of),
            avg_rate_by_currency={
                cur: (e["rate_w"] / e["rate_d"]) if e["rate_d"] else Decimal("0")
                for cur, e in by_currency.items()
            },
        )

    @staticmethod
    def _to_topref(
        ln: Optional[CreditPortfolioLoan], as_of: date_type
    ) -> Optional[TopLoanRef]:
        if ln is None:
            return None
        comp_name = (
            ln.company.name_ru
            if ln.company is not None and ln.company.name_ru
            else ""
        )
        return TopLoanRef(
            id=ln.id,
            loan_code=ln.loan_code,
            bank=ln.bank,
            bank_short_name=ln.bank_short_name or bank_short_name(ln.bank),
            company_name_ru=comp_name,
            debt_usd=Decimal(ln.debt_usd or 0),
            date_due=ln.date_due,
            days_until_due=days_between(as_of, ln.date_due) if ln.date_due else None,
            currency=ln.currency,
            debt_currency=Decimal(ln.debt_currency or 0),
            rate=Decimal(ln.rate) if ln.rate is not None else None,
        )

    # ─── Risk metrics ─────────────────────────────────────────────

    async def risk_metrics(
        self,
        user: User,
        *,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        as_of: Optional[date_type] = None,
    ) -> RiskMetrics:
        as_of = as_of or _DEFAULT_AS_OF
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio

            if company_code:
                co = await repo.get_company_by_code(company_code)
                if co is None:
                    raise HTTPException(
                        http_status.HTTP_404_NOT_FOUND, "Company not found"
                    )
                company_id = co.id

            scope = await self._scope_ids(user)
            loans = await repo.list_active_loans(
                company_id=company_id, allowed_company_ids=scope
            )

            total_usd = sum((Decimal(l.debt_usd or 0) for l in loans), Decimal("0"))
            weighted_rate = Decimal("0")
            rate_base = Decimal("0")
            annual_interest = Decimal("0")
            overdue_count = 0
            overdue_amount = Decimal("0")
            refi_12mo = Decimal("0")
            by_bank: dict[str, Decimal] = {}

            for ln in loans:
                debt_usd = Decimal(ln.debt_usd or 0)
                rate = ln.rate
                if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
                    weighted_rate += Decimal(rate) * debt_usd
                    rate_base += debt_usd

                bk = ln.bank_short_name or bank_short_name(ln.bank)
                by_bank[bk] = by_bank.get(bk, Decimal("0")) + debt_usd

                if ln.date_due is not None:
                    d = days_between(as_of, ln.date_due)
                    if d is not None:
                        if d < 0:
                            overdue_count += 1
                            overdue_amount += debt_usd
                        if 0 <= d <= 365:
                            refi_12mo += debt_usd

            avg_rate = (weighted_rate / rate_base) if rate_base > 0 else Decimal("0")
            for ln in loans:
                debt_usd = Decimal(ln.debt_usd or 0)
                rate = ln.rate
                if rate is not None and Decimal(0) < Decimal(rate) < Decimal(1):
                    annual_interest += debt_usd * Decimal(rate)
                else:
                    annual_interest += debt_usd * avg_rate

            refi_12mo_pct = float(refi_12mo / total_usd) if total_usd > 0 else 0.0
            top_bank_amt = max(by_bank.values()) if by_bank else Decimal("0")
            concentration_pct = float(top_bank_amt / total_usd) if total_usd > 0 else 0.0

            ebitda_usd, ebitda_year, ebitda_src, ebitda_unit, ebitda_sane = (
                await self._resolve_ebitda()
            )

        debt_to_ebitda = None
        icr = None
        if ebitda_sane and ebitda_usd and ebitda_usd > 0:
            debt_to_ebitda = total_usd / ebitda_usd if total_usd > 0 else None
            icr = ebitda_usd / annual_interest if annual_interest > 0 else None

        return RiskMetrics(
            ebitda_usd=ebitda_usd,
            ebitda_year=ebitda_year,
            ebitda_source_company=ebitda_src,
            ebitda_unit_assumed=ebitda_unit,
            ebitda_sane=ebitda_sane,
            debt_to_ebitda=debt_to_ebitda,
            icr=icr,
            annual_interest_expense_usd=annual_interest,
            refi_12mo_pct=refi_12mo_pct,
            concentration_top1_pct=concentration_pct,
            overdue_count=overdue_count,
            overdue_amount_usd=overdue_amount,
        )

    async def _resolve_ebitda(
        self,
    ) -> tuple[Optional[Decimal], Optional[int], Optional[str], Optional[str], bool]:
        """Must be called inside `async with self.uow`."""
        repo = self.uow.credit_portfolio
        co = await repo.get_ebitda_anchor_company()
        if co is None:
            return (None, None, None, None, False)

        rows = await repo.list_financials_for_company(co.id)
        fx_usd_uzs = _DEFAULT_USD_RATE

        for row in rows:
            ebitda_raw = None
            for attr in ("ebitda", "ebitda_uzs", "ebitda_usd"):
                if hasattr(row, attr):
                    v = getattr(row, attr)
                    if v is not None and v != 0:
                        ebitda_raw = Decimal(str(v))
                        break
            if ebitda_raw is None:
                continue

            if ebitda_raw > Decimal("1e9"):
                usd = ebitda_raw / fx_usd_uzs
                unit = "UZS (сумы)"
            elif ebitda_raw > Decimal("1e6"):
                usd = ebitda_raw * Decimal("1e6") / fx_usd_uzs
                unit = "млн UZS"
            elif ebitda_raw >= Decimal("100"):
                usd = ebitda_raw * Decimal("1e9") / fx_usd_uzs
                unit = "млрд UZS"
            elif ebitda_raw > 0:
                usd = ebitda_raw * Decimal("1e12") / fx_usd_uzs
                unit = "трлн UZS"
            else:
                continue

            sane = Decimal("1e8") < usd < Decimal("2e10")
            return (usd, row.year, co.name_ru or co.code, unit, sane)

        return (None, None, co.name_ru or co.code, None, False)

    # ─── Risk bubble + Sankey ─────────────────────────────────────

    async def risk_bubble(
        self,
        user: User,
        *,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        as_of: Optional[date_type] = None,
    ) -> list[RiskBubblePoint]:
        as_of = as_of or _DEFAULT_AS_OF
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio

            if company_code:
                co = await repo.get_company_by_code(company_code)
                if co is None:
                    raise HTTPException(
                        http_status.HTTP_404_NOT_FOUND, "Company not found"
                    )
                company_id = co.id

            scope = await self._scope_ids(user)
            loans = await repo.list_active_loans(
                company_id=company_id,
                date_due_required=True,
                rate_required=True,
                allowed_company_ids=scope,
            )

        points: list[RiskBubblePoint] = []
        for ln in loans:
            if ln.rate is None or Decimal(ln.rate) >= Decimal("1"):
                continue
            days = days_between(as_of, ln.date_due)
            if days is None:
                continue
            years_to = max(0.0, days / 365.25)
            points.append(RiskBubblePoint(
                loan_id=ln.id,
                loan_code=ln.loan_code,
                bank=ln.bank,
                bank_short_name=ln.bank_short_name or bank_short_name(ln.bank),
                currency=ln.currency,
                years_to_due=years_to,
                rate_pct=float(Decimal(ln.rate) * Decimal("100")),
                debt_usd=Decimal(ln.debt_usd or 0),
                date_due=ln.date_due,
            ))
        return points

    async def sankey(
        self,
        user: User,
        *,
        company_id: Optional[UUID] = None,
        company_code: Optional[str] = None,
        as_of: Optional[date_type] = None,
    ) -> list[SankeyFlow]:
        as_of = as_of or _DEFAULT_AS_OF
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio

            if company_code:
                co = await repo.get_company_by_code(company_code)
                if co is None:
                    raise HTTPException(
                        http_status.HTTP_404_NOT_FOUND, "Company not found"
                    )
                company_id = co.id

            scope = await self._scope_ids(user)
            loans = await repo.list_active_loans(
                company_id=company_id,
                date_due_required=True,
                allowed_company_ids=scope,
            )

        by_bank: dict[str, Decimal] = {}
        for ln in loans:
            bk = ln.bank_short_name or bank_short_name(ln.bank)
            by_bank[bk] = by_bank.get(bk, Decimal("0")) + Decimal(ln.debt_usd or 0)

        top_banks = {b for b, _ in sorted(by_bank.items(), key=lambda x: -x[1])[:8]}

        flows: dict[tuple[str, str], Decimal] = {}
        base_year = as_of.year
        for ln in loans:
            bk = ln.bank_short_name or bank_short_name(ln.bank)
            if bk not in top_banks:
                continue
            y = year_of(ln.date_due)
            if y is None or y < base_year:
                continue
            year_label = f">{base_year + 4}" if y > base_year + 4 else str(y)
            flows[(bk, year_label)] = flows.get(
                (bk, year_label), Decimal("0")
            ) + Decimal(ln.debt_usd or 0)

        return [
            SankeyFlow(bank_short_name=bk, year_label=y, debt_usd=v)
            for (bk, y), v in flows.items()
            if v > 0
        ]

    # ─── Companies overview (league table) ────────────────────────

    async def companies_overview(
        self, user: User, *, as_of: Optional[date_type] = None
    ) -> list[CompanyAggregateRow]:
        as_of = as_of or _DEFAULT_AS_OF
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio
            scope = await self._scope_ids(user)
            loans = await repo.list_active_loans(
                with_company_sector=True, allowed_company_ids=scope
            )
            if not loans:
                return []
            fx = await self._resolve_fx(repo, as_of)

        cur_year = as_of.year
        per_co: dict[UUID, dict] = {}

        for ln in loans:
            co = ln.company
            if co is None:
                continue
            debt_usd = Decimal(ln.debt_usd or 0)
            sum_total = Decimal(ln.sum_total or 0)

            if Decimal(ln.debt_currency or 0) > 0 and debt_usd > 0:
                sum_total_usd = sum_total * (debt_usd / Decimal(ln.debt_currency or 1))
            else:
                fx_cur = fx.get(ln.currency, Decimal("1"))
                fx_usd = fx.get("USD", _DEFAULT_USD_RATE)
                sum_total_usd = (sum_total * fx_cur / fx_usd) if fx_usd else Decimal("0")
            if sum_total_usd == 0 and debt_usd > 0:
                sum_total_usd = debt_usd

            bucket = per_co.setdefault(co.id, {
                "company": co,
                "loans_count": 0,
                "debt_usd": Decimal("0"),
                "loaned": Decimal("0"),
                "repaid": Decimal("0"),
                "rate_w": Decimal("0"),
                "rate_d": Decimal("0"),
                "pay_by_year": {},
                "pay_gt2032": Decimal("0"),
            })
            bucket["loans_count"] += 1
            bucket["debt_usd"] += debt_usd
            bucket["loaned"] += sum_total_usd
            bucket["repaid"] += max(Decimal("0"), sum_total_usd - debt_usd)

            if ln.rate is not None and Decimal(0) < Decimal(ln.rate) < Decimal(1):
                bucket["rate_w"] += Decimal(ln.rate) * debt_usd
                bucket["rate_d"] += debt_usd

            y = year_of(ln.date_due)
            if y is not None:
                if y > 2032:
                    bucket["pay_gt2032"] += debt_usd
                else:
                    bucket["pay_by_year"][y] = bucket["pay_by_year"].get(
                        y, Decimal("0")
                    ) + debt_usd

        rows: list[CompanyAggregateRow] = []
        for e in per_co.values():
            co = e["company"]
            sector_code = co.sector.code if co.sector else None
            sector_color = (
                (co.sector.color_hex if co.sector and co.sector.color_hex else None)
                or _FALLBACK_SECTOR_COLORS.get(sector_code or "", "#888780")
            )
            avg_rate = (e["rate_w"] / e["rate_d"]) if e["rate_d"] > 0 else Decimal("0")
            repaid_pct = float(e["repaid"] / e["loaned"]) if e["loaned"] > 0 else 0.0

            rows.append(CompanyAggregateRow(
                company_id=co.id,
                company_name_ru=co.name_ru or co.code,
                company_code=co.code,
                sector_code=sector_code,
                sector_color=sector_color,
                loans_count=e["loans_count"],
                debt_usd=e["debt_usd"],
                loaned_total_usd=e["loaned"],
                repaid_total_usd=e["repaid"],
                repaid_pct=repaid_pct,
                avg_rate=avg_rate,
                payment_this_year=e["pay_by_year"].get(cur_year, Decimal("0")),
                payment_next_year=e["pay_by_year"].get(cur_year + 1, Decimal("0")),
                pay_by_year=[
                    CompanyPaymentByYear(year=y, debt_usd=v)
                    for y, v in sorted(e["pay_by_year"].items())
                ],
                pay_gt2032=e["pay_gt2032"],
            ))
        rows.sort(key=lambda r: -r.debt_usd)
        return rows

    # ─── FX rates ─────────────────────────────────────────────────

    async def list_fx_rates(
        self, user: User, *, as_of: Optional[date_type] = None
    ) -> list[FxRateRead]:
        async with self.uow:
            await self._require(user, "credit.view")
            rows = await self.uow.credit_portfolio.list_fx_rates(as_of=as_of)
        return [FxRateRead.model_validate(r) for r in rows]

    async def upsert_fx_rate(
        self, payload: FxRateUpsert, user: User
    ) -> FxRateRead:
        async with self.uow:
            await self._require(user, "credit.edit")
            repo = self.uow.credit_portfolio
            rate = await repo.upsert_fx_rate(
                as_of=payload.as_of_date,
                currency=payload.currency.upper(),
                rate_to_uzs=payload.rate_to_uzs,
                notes=payload.notes,
            )
            await repo.flush()
            await repo.refresh(rate)
            return FxRateRead.model_validate(rate)

    # ─── Payments ─────────────────────────────────────────────────
    # NOTE: Helper `_get_loan_or_404_in_tx` MUST be called within an open uow.

    async def _get_loan_or_404_in_tx(
        self, loan_id: UUID, user: User
    ) -> CreditPortfolioLoan:
        repo = self.uow.credit_portfolio
        loan = await repo.get_loan(loan_id)
        if loan is None:
            raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Loan not found")
        await self._check_company_access(user, loan.company_id)
        return loan

    async def list_loan_payments(
        self,
        loan_id: UUID,
        user: User,
        *,
        include_deleted: bool = False,
    ) -> list[PaymentRead]:
        async with self.uow:
            await self._require(user, "credit.view")
            await self._get_loan_or_404_in_tx(loan_id, user)
            rows = await self.uow.credit_portfolio.list_payments_for_loan(
                loan_id, include_deleted=include_deleted
            )
        return [PaymentRead.model_validate(p) for p in rows]

    async def create_loan_payment(
        self, loan_id: UUID, payload: PaymentCreate, user: User
    ) -> PaymentRead:
        async with self.uow:
            await self._require(user, "credit.edit")
            loan = await self._get_loan_or_404_in_tx(loan_id, user)

            if (payload.principal_paid < 0
                or payload.interest_paid < 0
                or payload.penalty_paid < 0):
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    "Суммы платежа не могут быть отрицательными",
                )

            repo = self.uow.credit_portfolio
            payment = CreditPortfolioPayment(
                loan_id=loan_id,
                paid_date=payload.paid_date,
                principal_paid=payload.principal_paid,
                interest_paid=payload.interest_paid,
                penalty_paid=payload.penalty_paid,
                currency=loan.currency,
                fx_rate_to_uzs=payload.fx_rate_to_uzs,
                note=payload.note,
                created_by_user_id=user.id,
            )
            repo.add(payment)
            await repo.flush()
            await self._recompute_loan_debt(loan_id)
            await repo.flush()
            await repo.refresh(payment)
            return PaymentRead.model_validate(payment)

    async def get_payment(self, payment_id: UUID, user: User) -> PaymentRead:
        async with self.uow:
            await self._require(user, "credit.view")
            repo = self.uow.credit_portfolio
            payment = await repo.get_payment(payment_id)
            if payment is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Payment not found")
            await self._get_loan_or_404_in_tx(payment.loan_id, user)
            return PaymentRead.model_validate(payment)

    async def update_payment(
        self, payment_id: UUID, payload: PaymentUpdate, user: User
    ) -> PaymentRead:
        async with self.uow:
            await self._require(user, "credit.edit")
            repo = self.uow.credit_portfolio
            payment = await repo.get_payment(payment_id)
            if payment is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Payment not found")
            await self._get_loan_or_404_in_tx(payment.loan_id, user)
            if payment.deleted_at is not None:
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    "Платёж удалён — восстановите перед редактированием",
                )

            data = payload.model_dump(exclude_unset=True)
            for k, v in data.items():
                setattr(payment, k, v)
            if ((payment.principal_paid or 0) < 0
                or (payment.interest_paid or 0) < 0
                or (payment.penalty_paid or 0) < 0):
                raise HTTPException(
                    http_status.HTTP_400_BAD_REQUEST,
                    "Суммы платежа не могут быть отрицательными",
                )

            await repo.flush()
            await self._recompute_loan_debt(payment.loan_id)
            await repo.flush()
            await repo.refresh(payment)
            return PaymentRead.model_validate(payment)

    async def delete_payment(self, payment_id: UUID, user: User) -> None:
        async with self.uow:
            await self._require(user, "credit.edit")
            repo = self.uow.credit_portfolio
            payment = await repo.get_payment(payment_id)
            if payment is None:
                raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Payment not found")
            await self._get_loan_or_404_in_tx(payment.loan_id, user)
            if payment.deleted_at is None:
                payment.deleted_at = date_type.today()
                await repo.flush()
                await self._recompute_loan_debt(payment.loan_id)

    async def loan_payments_summary(
        self, loan_id: UUID, user: User
    ) -> LoanPaymentsSummary:
        async with self.uow:
            await self._require(user, "credit.view")
            await self._get_loan_or_404_in_tx(loan_id, user)
            row = await self.uow.credit_portfolio.payment_aggregate(loan_id)
        return LoanPaymentsSummary(
            loan_id=loan_id,
            payments_count=row.cnt,
            total_principal_paid=Decimal(row.p or 0),
            total_interest_paid=Decimal(row.i or 0),
            total_penalty_paid=Decimal(row.e or 0),
            last_paid_date=row.last,
        )

    async def _recompute_loan_debt(self, loan_id: UUID) -> None:
        """Must be called inside `async with self.uow` after the payment
        change has been flushed.

        Recalculates `debt_currency` and `debt_usd` from the active payments
        baseline. If all payments are removed, baseline clears and loan
        reverts to its snapshot value.
        """
        repo = self.uow.credit_portfolio
        loan = await repo.get_loan(loan_id)
        if loan is None:
            return

        total_principal, last_paid_date, active_count = (
            await repo.active_payments_summary(loan_id)
        )

        if active_count == 0:
            if loan.payments_baseline_debt is not None:
                loan.debt_currency = loan.payments_baseline_debt
            loan.payments_baseline_debt = None
            loan.payments_started_at = None
            return

        if loan.payments_baseline_debt is None:
            if loan.debt_currency is not None:
                loan.payments_baseline_debt = loan.debt_currency
            else:
                loan.payments_baseline_debt = (
                    loan.sum_disbursed if loan.sum_disbursed is not None
                    else (loan.sum_total or Decimal("0"))
                )
            loan.payments_started_at = last_paid_date

        new_debt_cur = (loan.payments_baseline_debt or Decimal("0")) - total_principal
        if new_debt_cur < 0:
            new_debt_cur = Decimal("0")
        loan.debt_currency = new_debt_cur

        if loan.currency == "USD":
            loan.debt_usd = new_debt_cur
        elif loan.currency == "UZS":
            usd_rate = await repo.latest_currency_rate("USD")
            if usd_rate and usd_rate > 0:
                loan.debt_usd = (new_debt_cur / usd_rate).quantize(Decimal("0.01"))
        else:
            cur_to_uzs = await repo.latest_currency_rate(loan.currency)
            usd_to_uzs = await repo.latest_currency_rate("USD")
            if cur_to_uzs and usd_to_uzs and usd_to_uzs > 0:
                loan.debt_usd = (
                    new_debt_cur * cur_to_uzs / usd_to_uzs
                ).quantize(Decimal("0.01"))

        if last_paid_date is not None:
            loan.as_of_date = last_paid_date
