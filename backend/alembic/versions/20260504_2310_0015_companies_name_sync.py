"""auto-sync boards.name when companies.name_short changes

Revision ID: 0015_companies_name_sync
Revises: 0014_company_link_sweep
Create Date: 2026-05-04 23:10:00.000000

Companies admin editor is the single source of truth for company names.
When the operator edits `companies.name_short` (e.g. renames "Узавтосаноат"
→ "УзАвтоСаноат"), this change must propagate immediately to every
denormalised place that displays the company name — most notably
`boards.name`, which is shown in Boards/Projects/Tasks lists.

Without this trigger, the operator would edit name_short and see the
update everywhere EXCEPT the boards-driven views — because boards.name
was a one-time normalisation done in 0013/0014.

Implementation:
  - AFTER UPDATE trigger on companies
  - When name_short OLD <> NEW: set boards.name = NEW.name_short
    for every board with company_id = NEW.id
  - Snapshots the previous board.name into extra.legacy_name_history
    (append, not overwrite) so the rename history is auditable

Note: API-level views (FinancialReport.company_name etc.) already read
Company.name_short live via JOIN — no change needed for those.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0015_companies_name_sync"
down_revision: Union[str, None] = "0014_company_link_sweep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Trigger function — runs after companies.name_short is changed.
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_boards_name_on_company_rename()
        RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.name_short IS NOT NULL
               AND NEW.name_short <> ''
               AND COALESCE(OLD.name_short, '') <> COALESCE(NEW.name_short, '')
            THEN
                UPDATE boards b
                SET    name = NEW.name_short,
                       extra = COALESCE(b.extra, '{}'::jsonb)
                               || jsonb_build_object(
                                    'last_renamed_at', to_jsonb(NOW()),
                                    'last_legacy_name', to_jsonb(b.name)
                                  ),
                       updated_at = NOW()
                WHERE  b.company_id = NEW.id
                  AND  b.name <> NEW.name_short;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_sync_boards_name_on_company_rename ON companies;
        CREATE TRIGGER trg_sync_boards_name_on_company_rename
            AFTER UPDATE OF name_short ON companies
            FOR EACH ROW
            EXECUTE FUNCTION sync_boards_name_on_company_rename();
    """)

    # Also: when a board is FIRST linked to a company (company_id changes from
    # NULL/other to set), its name should snap to the canonical name_short.
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_board_name_on_link()
        RETURNS TRIGGER AS $$
        DECLARE
            canonical_short TEXT;
        BEGIN
            -- Only act when company_id changed and is now set
            IF NEW.company_id IS NOT NULL
               AND NEW.company_id IS DISTINCT FROM OLD.company_id
            THEN
                SELECT c.name_short INTO canonical_short
                FROM   companies c
                WHERE  c.id = NEW.company_id;

                IF canonical_short IS NOT NULL
                   AND canonical_short <> ''
                   AND canonical_short <> NEW.name
                THEN
                    NEW.name := canonical_short;
                    NEW.extra := COALESCE(NEW.extra, '{}'::jsonb)
                                 || jsonb_build_object('legacy_name', OLD.name);
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_sync_board_name_on_link ON boards;
        CREATE TRIGGER trg_sync_board_name_on_link
            BEFORE UPDATE OF company_id ON boards
            FOR EACH ROW
            EXECUTE FUNCTION sync_board_name_on_link();
    """)

    # And: same on INSERT — a new board with company_id should adopt name_short
    # immediately, even if the operator typed a different name in the new-board form.
    op.execute("""
        CREATE OR REPLACE FUNCTION sync_board_name_on_insert()
        RETURNS TRIGGER AS $$
        DECLARE
            canonical_short TEXT;
        BEGIN
            IF NEW.company_id IS NOT NULL THEN
                SELECT c.name_short INTO canonical_short
                FROM   companies c
                WHERE  c.id = NEW.company_id;

                IF canonical_short IS NOT NULL
                   AND canonical_short <> ''
                   AND canonical_short <> NEW.name
                THEN
                    NEW.extra := COALESCE(NEW.extra, '{}'::jsonb)
                                 || jsonb_build_object('intended_name', NEW.name);
                    NEW.name := canonical_short;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        DROP TRIGGER IF EXISTS trg_sync_board_name_on_insert ON boards;
        CREATE TRIGGER trg_sync_board_name_on_insert
            BEFORE INSERT ON boards
            FOR EACH ROW
            EXECUTE FUNCTION sync_board_name_on_insert();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_sync_boards_name_on_company_rename ON companies;")
    op.execute("DROP TRIGGER IF EXISTS trg_sync_board_name_on_link ON boards;")
    op.execute("DROP TRIGGER IF EXISTS trg_sync_board_name_on_insert ON boards;")
    op.execute("DROP FUNCTION IF EXISTS sync_boards_name_on_company_rename();")
    op.execute("DROP FUNCTION IF EXISTS sync_board_name_on_link();")
    op.execute("DROP FUNCTION IF EXISTS sync_board_name_on_insert();")
