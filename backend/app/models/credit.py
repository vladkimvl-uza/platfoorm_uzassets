"""
Credit Portfolio module — мигрирует модуль "Кредитный портфель" из монолита.

Schema mirrors monolith data structure 1:1 (see CP_LOANS_*_DEFAULT in
index.html line 24121+). Each row = one loan tranche with original loan
ID, currency, rate, debt outstanding (in original currency + USD), dates,
lender classification.

Tables:
  cp_loans        — loan registry (~316 rows in production today)
  cp_fx_rates     — FX rates by snapshot date (mirrors CP_RATES_FX)
"""
from typing import Optional
from decimal import Decimal
from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import UUID as PyUUID

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


# Allowed values (kept lowercase for normalization)
CP_CURRENCIES = ("USD", "EUR", "CNY", "JPY", "RUB", "SDR", "UZS", "KZT", "GBP")
CP_LENDER_TYPES = ("bond", "foreign", "local", "state")


class CreditPortfolioLoan(Base, UUIDMixin, TimestampMixin):
    """One loan tranche in the consolidated portfolio.

    Matches monolith fields 1:1 — see CP_LOANS_*_DEFAULT decoded JSON.
    """

    __tablename__ = "cp_loans"

    # Original ID from the monolith ("L001", "UZAP001", etc.) — kept for
    # idempotent re-import and traceability.
    loan_code: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )

    # Portfolio company FK. Companies are matched by Russian name during the
    # initial import; future inserts use FK directly.
    company_id: Mapped[PyUUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional sub-unit (e.g. "Сирдарё ИЭС филиали" for ТЭС, etc.)
    borrower_unit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # The lender (bank or other counterparty) — exact name from monolith
    bank: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bank_short_name: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )  # cached normalized name for grouping (e.g. "Узпромстройбанк" → "УПСБ")

    contract_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Currency code: USD/EUR/CNY/JPY/RUB/SDR/UZS — checked at app level
    currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)

    # Effective interest rate as DECIMAL fraction (0.0212 = 2.12%)
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    # Display string (e.g. "SHIBOR 6M + 0.50%", "EURIBOR 3M + 1.75%")
    rate_text: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Original facility size in `currency`
    sum_total: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    # Disbursed (drawn) amount in `currency` — for project finance lines
    sum_disbursed: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # Outstanding debt as of as_of_date (source of truth for portfolio totals)
    debt_currency: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    debt_usd: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(20, 2), nullable=True
    )

    # Dates
    date_get: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_due: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    # State guarantee flag
    is_guaranteed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    # Lender type: bond/foreign/local/state. Auto-classified from `bank` if
    # not set, but an explicit override may be stored.
    lender_type: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, index=True
    )

    # Editor "auto vs manual" flags. The monolith stores per-field which were
    # auto-computed (e.g. debtUsd derived from FX) vs manually overridden.
    auto_flags: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Free-text notes
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # As-of date for `debt_*` fields
    as_of_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Soft delete
    deleted_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)

    # Auditing
    created_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[Optional[PyUUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    company = relationship("Company", lazy="select")


# Composite indexes for common aggregations
Index("ix_cp_loans_co_currency", CreditPortfolioLoan.company_id, CreditPortfolioLoan.currency)
Index("ix_cp_loans_lender_type_idx", CreditPortfolioLoan.lender_type)
Index(
    "ix_cp_loans_active",
    CreditPortfolioLoan.company_id,
    CreditPortfolioLoan.deleted_at,
)


class CreditPortfolioFxRate(Base, UUIDMixin, TimestampMixin):
    """FX rate snapshot for a given as-of date.

    Mirrors `CP_RATES_FX` constant in the monolith. Storing as a table
    rather than constants lets the editor adjust rates and compare USD
    valuations across multiple snapshot dates.
    """

    __tablename__ = "cp_fx_rates"

    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    # 1 unit of `currency` = N UZS
    rate_to_uzs: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("as_of_date", "currency", name="uq_cp_fx_date_cur"),
    )
