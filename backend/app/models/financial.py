"""Financial reports: balance sheet, income statement, cash flow.
Supports both IFRS and NSBU (Uzbek national standards)."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class FinancialReport(Base, UUIDMixin, TimestampMixin):
    """A financial report for a company in a given period."""

    __tablename__ = "financial_reports"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "year", "quarter", "standard", "report_type", "is_consolidated",
            name="uq_fin_report_co_year_qtr_std_type_scope",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ifrs | nsbu
    standard: Mapped[str] = mapped_column(String(8), nullable=False, index=True)

    # bs | pl | cf — balance sheet, profit & loss, cash flow
    report_type: Mapped[str] = mapped_column(String(8), nullable=False, index=True)

    # Currency: UZS | USD | EUR | RUB
    currency: Mapped[str] = mapped_column(String(8), default="UZS", nullable=False)

    # Unit scale: множитель value → абсолютные сумы. Канон платформы:
    # value хранится в МЛРД → unit_scale=1e9 (аудит фин-источников P1;
    # старый default 1000 был неверным флагом — данные всегда были в млрд).
    unit_scale: Mapped[int] = mapped_column(
        Integer, default=1_000_000_000, nullable=False,
    )

    # Source of data: import | manual | api | excel-confirm:<filename>
    source: Mapped[str] = mapped_column(String(255), default="manual", nullable=False)

    is_audited: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_detailed: Mapped[bool] = mapped_column(
        default=False, nullable=False,
        doc="True for detailed audit reports (sub-line items); "
            "False for summary 26-field reports from /pf/financials"
    )
    # (IFRS-editor): True for consolidated/group reports (default),
    # False for standalone/parent-only reports. NSBU always = True.
    is_consolidated: Mapped[bool] = mapped_column(default=True, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    lines: Mapped[list["FinancialLine"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class FinancialLine(Base, UUIDMixin, TimestampMixin):
    """A single line item on a financial report."""

    __tablename__ = "financial_lines"

    report_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_reports.id", ondelete="CASCADE"), index=True
    )

    # Hierarchical code: 1, 1.1, 1.1.1
    line_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    parent_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    section_label: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
        doc="Group header rendered before this line (e.g. 'ASSETS', 'EQUITY')"
    )
    indent_level: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        doc="Indent depth: 0=top, 1=sub, 2=sub-sub"
    )
    line_name: Mapped[str] = mapped_column(String(512), nullable=False)
    line_name_uz: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    line_name_en: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 4), nullable=True)
    prev_year_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(28, 4), nullable=True)

    is_subtotal: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_calculated: Mapped[bool] = mapped_column(default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    report: Mapped["FinancialReport"] = relationship(back_populates="lines")


Index("ix_fin_lines_report_code", FinancialLine.report_id, FinancialLine.line_code)
