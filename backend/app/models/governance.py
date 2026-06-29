"""Corporate governance: board composition, committees, raw Excel data.
Critical: keep `governance_data` (structured, editable) separate from
`governance_raw` (raw Excel snapshots for AI context) — see lessons-learned."""
from datetime import date
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class GovernanceData(Base, UUIDMixin, TimestampMixin):
    """Structured editable governance data per company per year.
    Mirrors `_db.governanceData` in the legacy."""

    __tablename__ = "governance_data"
    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_gov_data_co_year"),
    )

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    board_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    independent_directors_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    women_directors_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    foreign_directors_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    has_audit_committee: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_remuneration_committee: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_nomination_committee: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_strategy_committee: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    meetings_per_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_attendance_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GovernanceRaw(Base, UUIDMixin, TimestampMixin):
    """Raw Excel snapshot for AI context.
    Mirrors `_db.govData` in the legacy — never conflate with `governance_data`."""

    __tablename__ = "governance_raw"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    source_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_sheet: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class BoardMember(Base, UUIDMixin, TimestampMixin):
    """An individual member of a board of directors / supervisory board."""

    __tablename__ = "board_members"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # chairman | independent | state_rep

    is_independent: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_woman: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_foreign: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    appointed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    term_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


Index("ix_board_members_co_active", BoardMember.company_id, BoardMember.term_end_date)


class CommitteeMeeting(Base, UUIDMixin, TimestampMixin):
    """Количество заседаний наблюдательного совета и его комитетов за период.

    Период задаётся парой (year, quarter): quarter NULL = годовой/полный период,
    1..4 = соответствующий квартал. Уникальность по (company_id, year, quarter)
    обеспечивается двумя partial unique индексами в runtime_migrations
    (NULL в Postgres считается distinct), потому в ORM constraint не объявляем.
    """

    __tablename__ = "committee_meetings"

    company_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    # NULL = годовой/полный период; 1..4 = квартал.

    sb_meetings: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Заседания наблюдательного совета — количество
    sb_decisions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Решения, принятые протоколом — количество

    audit_mtg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)       # Аудит
    strategy_mtg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # Стратегия и инвестиции
    nomrem_mtg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)      # Назначения и вознаграждения
    anticorr_mtg: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # Антикоррупция и этика


Index("ix_cmtg_year_quarter", CommitteeMeeting.year, CommitteeMeeting.quarter)
