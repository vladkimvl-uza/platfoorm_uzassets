"""notes smart journal: company_id, kind, tags, dates, resolution + note_links

Revision ID: 0024_notes_smart_journal
Revises: 7c29bd804fae
Create Date: 2026-05-08 15:00:00

Расширение `notes` под Smart Journal архитектуры B+C:
- company_id NULLable FK -> companies (главный scope для company workspace)
- kind VARCHAR(32) NOT NULL DEFAULT 'observation'
  (event/decision/task/risk/observation)
- tags TEXT[] NOT NULL DEFAULT '{}' (GIN index)
- event_date TIMESTAMPTZ NULL (когда это произошло)
- due_date TIMESTAMPTZ NULL (дедлайн для kind=task)
- is_resolved BOOLEAN NOT NULL DEFAULT FALSE
- resolved_at TIMESTAMPTZ NULL
- author_id UUID NULL FK -> users (кто создал заметку; user_id -- legacy)

Новая таблица `note_links` для polymorphic ссылок на сущности:
- entity_type (project/task/kpi_indicator/kpi_manager/esg_issue/board_member/loan/consultant/bp_metric)
- entity_id UUID NULL (для UUID-ссылок)
- entity_key VARCHAR(128) NULL (для не-UUID, e.g. bp_metric="revenue")
- entity_label VARCHAR(255) NULL (cached display)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0024_notes_smart_journal"
down_revision = "7c29bd804fae"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === [1] notes: новые колонки ===
    op.add_column(
        "notes",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="observation",
        ),
    )
    op.add_column(
        "notes",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )
    op.add_column(
        "notes",
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notes",
        sa.Column(
            "is_resolved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "notes",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # FK on company_id и author_id
    op.create_foreign_key(
        "fk_notes_company_id",
        "notes",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_notes_author_id",
        "notes",
        "users",
        ["author_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # CHECK constraint на kind
    op.create_check_constraint(
        "ck_notes_kind",
        "notes",
        "kind IN ('event','decision','task','risk','observation')",
    )

    # === [2] notes: индексы ===
    op.create_index(
        "ix_notes_company",
        "notes",
        ["company_id", sa.text("event_date DESC NULLS LAST")],
    )
    op.create_index("ix_notes_kind", "notes", ["kind"])
    op.create_index("ix_notes_author_id", "notes", ["author_id"])
    op.create_index("ix_notes_due_date", "notes", ["due_date"])
    # GIN на tags для содержит/contains запросов
    op.create_index(
        "ix_notes_tags_gin",
        "notes",
        ["tags"],
        postgresql_using="gin",
    )

    # === [3] note_links table ===
    op.create_table(
        "note_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "note_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_key", sa.String(length=128), nullable=True),
        sa.Column("entity_label", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_note_links_note_id", "note_links", ["note_id"])
    op.create_index(
        "ix_note_links_entity",
        "note_links",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_note_links_entity_key",
        "note_links",
        ["entity_type", "entity_key"],
    )
    op.create_check_constraint(
        "ck_note_links_entity_ref",
        "note_links",
        "entity_id IS NOT NULL OR entity_key IS NOT NULL",
    )


def downgrade() -> None:
    # === note_links ===
    op.drop_constraint("ck_note_links_entity_ref", "note_links", type_="check")
    op.drop_index("ix_note_links_entity_key", table_name="note_links")
    op.drop_index("ix_note_links_entity", table_name="note_links")
    op.drop_index("ix_note_links_note_id", table_name="note_links")
    op.drop_table("note_links")

    # === notes индексы ===
    op.drop_index("ix_notes_tags_gin", table_name="notes")
    op.drop_index("ix_notes_due_date", table_name="notes")
    op.drop_index("ix_notes_author_id", table_name="notes")
    op.drop_index("ix_notes_kind", table_name="notes")
    op.drop_index("ix_notes_company", table_name="notes")

    # === notes constraints ===
    op.drop_constraint("ck_notes_kind", "notes", type_="check")
    op.drop_constraint("fk_notes_author_id", "notes", type_="foreignkey")
    op.drop_constraint("fk_notes_company_id", "notes", type_="foreignkey")

    # === notes колонки ===
    op.drop_column("notes", "resolved_at")
    op.drop_column("notes", "is_resolved")
    op.drop_column("notes", "due_date")
    op.drop_column("notes", "event_date")
    op.drop_column("notes", "tags")
    op.drop_column("notes", "kind")
    op.drop_column("notes", "author_id")
    op.drop_column("notes", "company_id")
