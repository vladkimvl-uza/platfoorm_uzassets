"""Persistence layer for the Credit Portfolio module.

All SQL/ORM access lives here. Routes/service consume `CreditPortfolioRepository`
via the UnitOfWork (`uow.credit_portfolio`).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date as date_type
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.company import Company, Sector
from app.models.credit import (
    CreditPortfolioFxRate,
    CreditPortfolioLoan,
    CreditPortfolioPayment,
)


class CreditPortfolioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ─── Generic mutation helpers ─────────────────────────────────

    def add(self, obj: Any) -> None:
        self._session.add(obj)

    async def flush(self) -> None:
        await self._session.flush()

    async def refresh(self, obj: Any) -> None:
        await self._session.refresh(obj)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    # ─── Companies (lookup) ───────────────────────────────────────

    async def get_company_by_id(self, company_id: UUID) -> Optional[Company]:
        return (
            await self._session.execute(
                select(Company).where(Company.id == company_id)
            )
        ).scalar_one_or_none()

    async def get_company_by_code(self, code: str) -> Optional[Company]:
        return (
            await self._session.execute(
                select(Company).where(func.lower(Company.code) == code.lower())
            )
        ).scalar_one_or_none()

    async def list_all_companies(self) -> Sequence[Company]:
        return (await self._session.execute(select(Company))).scalars().all()

    # ─── Loans (read) ─────────────────────────────────────────────

    async def get_loan(
        self, loan_id: UUID, *, with_company: bool = False
    ) -> Optional[CreditPortfolioLoan]:
        q = select(CreditPortfolioLoan).where(CreditPortfolioLoan.id == loan_id)
        if with_company:
            q = q.options(selectinload(CreditPortfolioLoan.company))
        return (await self._session.execute(q)).scalar_one_or_none()

    async def get_loan_by_code(self, loan_code: str) -> Optional[CreditPortfolioLoan]:
        return (
            await self._session.execute(
                select(CreditPortfolioLoan).where(
                    CreditPortfolioLoan.loan_code == loan_code
                )
            )
        ).scalar_one_or_none()

    async def list_loans_filtered(
        self,
        *,
        company_id: Optional[UUID] = None,
        currency: Optional[str] = None,
        lender_type: Optional[str] = None,
        search: Optional[str] = None,
        include_deleted: bool = False,
        allowed_company_ids: Optional[set[UUID]] = None,
        with_company: bool = True,
    ) -> Sequence[CreditPortfolioLoan]:
        q = select(CreditPortfolioLoan)
        if with_company:
            q = q.options(selectinload(CreditPortfolioLoan.company))
        if not include_deleted:
            q = q.where(CreditPortfolioLoan.deleted_at.is_(None))
        if company_id is not None:
            q = q.where(CreditPortfolioLoan.company_id == company_id)
        if currency:
            q = q.where(CreditPortfolioLoan.currency == currency.upper())
        if lender_type:
            q = q.where(CreditPortfolioLoan.lender_type == lender_type)
        if search:
            like = f"%{search}%"
            q = q.where(
                CreditPortfolioLoan.bank.ilike(like)
                | CreditPortfolioLoan.contract_ref.ilike(like)
            )
        if allowed_company_ids is not None:
            q = q.where(CreditPortfolioLoan.company_id.in_(list(allowed_company_ids)))
        q = q.order_by(CreditPortfolioLoan.debt_usd.desc().nullslast())
        return (await self._session.execute(q)).scalars().unique().all()

    async def list_active_loans(
        self,
        *,
        company_id: Optional[UUID] = None,
        with_company: bool = False,
        with_company_sector: bool = False,
        date_due_required: bool = False,
        rate_required: bool = False,
        allowed_company_ids: Optional[set[UUID]] = None,
    ) -> Sequence[CreditPortfolioLoan]:
        q = select(CreditPortfolioLoan).where(CreditPortfolioLoan.deleted_at.is_(None))
        if with_company_sector:
            q = q.options(
                selectinload(CreditPortfolioLoan.company).selectinload(Company.sector)
            )
        elif with_company:
            q = q.options(selectinload(CreditPortfolioLoan.company))
        if date_due_required:
            q = q.where(CreditPortfolioLoan.date_due.is_not(None))
        if rate_required:
            q = q.where(CreditPortfolioLoan.rate.is_not(None))
        if company_id is not None:
            q = q.where(CreditPortfolioLoan.company_id == company_id)
        if allowed_company_ids is not None:
            q = q.where(CreditPortfolioLoan.company_id.in_(list(allowed_company_ids)))
        return (await self._session.execute(q)).scalars().unique().all()

    async def list_companies_with_loans(
        self, *, allowed_company_ids: Optional[set[UUID]] = None
    ) -> Sequence[Any]:
        q = (
            select(
                Company.id,
                Company.code,
                Company.name_ru,
                Sector.code.label("sector_code"),
                Sector.color_hex.label("sector_color"),
                func.count(CreditPortfolioLoan.id).label("cnt"),
                func.coalesce(func.sum(CreditPortfolioLoan.debt_usd), 0).label("debt"),
            )
            .join(CreditPortfolioLoan, CreditPortfolioLoan.company_id == Company.id)
            .outerjoin(Sector, Company.sector_id == Sector.id)
            .where(CreditPortfolioLoan.deleted_at.is_(None))
            .group_by(
                Company.id,
                Company.code,
                Company.name_ru,
                Sector.code,
                Sector.color_hex,
            )
            .order_by(func.sum(CreditPortfolioLoan.debt_usd).desc().nullslast())
        )
        if allowed_company_ids is not None:
            q = q.where(Company.id.in_(list(allowed_company_ids)))
        return (await self._session.execute(q)).all()

    # ─── FX rates ─────────────────────────────────────────────────

    async def list_fx_rates(
        self, *, as_of: Optional[date_type] = None
    ) -> Sequence[CreditPortfolioFxRate]:
        q = select(CreditPortfolioFxRate)
        if as_of:
            q = q.where(CreditPortfolioFxRate.as_of_date == as_of)
        q = q.order_by(
            CreditPortfolioFxRate.as_of_date.desc(),
            CreditPortfolioFxRate.currency,
        )
        return (await self._session.execute(q)).scalars().all()

    async def fx_rates_for(self, as_of: date_type) -> Sequence[CreditPortfolioFxRate]:
        return (
            await self._session.execute(
                select(CreditPortfolioFxRate).where(
                    CreditPortfolioFxRate.as_of_date == as_of
                )
            )
        ).scalars().all()

    async def latest_fx_date(self) -> Optional[date_type]:
        row = (
            await self._session.execute(
                select(CreditPortfolioFxRate.as_of_date)
                .order_by(CreditPortfolioFxRate.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return row

    async def latest_currency_rate(self, currency: str) -> Optional[Decimal]:
        row = (
            await self._session.execute(
                select(CreditPortfolioFxRate.rate_to_uzs)
                .where(CreditPortfolioFxRate.currency == currency)
                .order_by(CreditPortfolioFxRate.as_of_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return row

    async def upsert_fx_rate(
        self, *, as_of: date_type, currency: str, rate_to_uzs: Decimal,
        notes: Optional[str],
    ) -> CreditPortfolioFxRate:
        existing = (
            await self._session.execute(
                select(CreditPortfolioFxRate).where(
                    and_(
                        CreditPortfolioFxRate.as_of_date == as_of,
                        CreditPortfolioFxRate.currency == currency,
                    )
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.rate_to_uzs = rate_to_uzs
            existing.notes = notes
            return existing
        rate = CreditPortfolioFxRate(
            as_of_date=as_of,
            currency=currency,
            rate_to_uzs=rate_to_uzs,
            notes=notes,
        )
        self._session.add(rate)
        return rate

    # ─── Payments ─────────────────────────────────────────────────

    async def get_payment(self, payment_id: UUID) -> Optional[CreditPortfolioPayment]:
        return (
            await self._session.execute(
                select(CreditPortfolioPayment).where(
                    CreditPortfolioPayment.id == payment_id
                )
            )
        ).scalar_one_or_none()

    async def list_payments_for_loan(
        self, loan_id: UUID, *, include_deleted: bool = False
    ) -> Sequence[CreditPortfolioPayment]:
        q = select(CreditPortfolioPayment).where(
            CreditPortfolioPayment.loan_id == loan_id
        )
        if not include_deleted:
            q = q.where(CreditPortfolioPayment.deleted_at.is_(None))
        q = q.order_by(
            CreditPortfolioPayment.paid_date.desc(),
            CreditPortfolioPayment.created_at.desc(),
        )
        return (await self._session.execute(q)).scalars().all()

    async def payment_aggregate(self, loan_id: UUID) -> Any:
        return (
            await self._session.execute(
                select(
                    func.count().label("cnt"),
                    func.coalesce(
                        func.sum(CreditPortfolioPayment.principal_paid), 0
                    ).label("p"),
                    func.coalesce(
                        func.sum(CreditPortfolioPayment.interest_paid), 0
                    ).label("i"),
                    func.coalesce(
                        func.sum(CreditPortfolioPayment.penalty_paid), 0
                    ).label("e"),
                    func.max(CreditPortfolioPayment.paid_date).label("last"),
                ).where(
                    and_(
                        CreditPortfolioPayment.loan_id == loan_id,
                        CreditPortfolioPayment.deleted_at.is_(None),
                    )
                )
            )
        ).one()

    async def active_payments_summary(self, loan_id: UUID) -> tuple[Decimal, Optional[date_type], int]:
        row = (
            await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(CreditPortfolioPayment.principal_paid), 0
                    ).label("p"),
                    func.max(CreditPortfolioPayment.paid_date).label("last"),
                    func.count().label("cnt"),
                ).where(
                    and_(
                        CreditPortfolioPayment.loan_id == loan_id,
                        CreditPortfolioPayment.deleted_at.is_(None),
                    )
                )
            )
        ).one()
        return Decimal(row.p or 0), row.last, int(row.cnt)

    # ─── EBITDA anchor lookup (for risk metrics) ──────────────────

    async def get_ebitda_anchor_company(self) -> Optional[Company]:
        co = (
            await self._session.execute(
                select(Company).where(
                    Company.module_flags["ebitda_anchor"].astext == "true"
                )
            )
        ).scalar_one_or_none()
        if co is not None:
            return co
        return (
            await self._session.execute(
                select(Company).where(
                    func.lower(Company.code).in_(
                        ["ung", "uzneftgaz", "uzbekneftegaz"]
                    )
                )
            )
        ).scalar_one_or_none()

    async def list_financials_for_company(self, company_id: UUID) -> Sequence[Any]:
        """Best-effort lookup of FinancialsDetailed rows. Returns [] if model
        is missing or query fails — caller treats absence as 'no EBITDA'."""
        try:
            from app.models.financials_detailed import FinancialsDetailed  # type: ignore
        except Exception:
            return []
        try:
            return (
                await self._session.execute(
                    select(FinancialsDetailed)
                    .where(FinancialsDetailed.company_id == company_id)
                    .order_by(FinancialsDetailed.year.desc())
                )
            ).scalars().all()
        except Exception:
            return []
