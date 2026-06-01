"""Global year registry — single source of truth for what years are tracked.
Mirrors `window.YearRegistry` API in the monolith.
All year selectors must use this — no hardcoded year arrays."""
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class YearRegistry(Base, UUIDMixin, TimestampMixin):
    """A single tracked year and its global parameters
    (inflation index, USD rate, EUR rate, UZ Republic budget, etc.)."""

    __tablename__ = "year_registry"
    __table_args__ = (
        UniqueConstraint("year", name="uq_year_registry_year"),
    )

    year: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)

    # Annual inflation rate (Uzbekistan)
    inflation_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)

    # Average USD/UZS exchange rate (среднегодовой курс ЦБ РУ)
    usd_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Pack 7.37: средний EUR/UZS exchange rate (среднегодовой ЦБ РУ)
    eur_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)

    # Central bank base rate
    cb_rate_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)

    # GDP growth rate
    gdp_growth_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4), nullable=True)

    # Pack 7.35: доходная часть бюджета Республики Узбекистан, трлн сум.
    uz_budget_trln: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)

    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
