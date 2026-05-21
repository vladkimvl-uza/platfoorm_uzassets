"""attachments: result + company-wide docs (Pack 149)

Extends TaskAttachment model and adds CompanyAttachment for general
documents stored against a company (not tied to a specific task/project).

Schema:
  task_attachments.storage_key    — opaque storage key (S3 or local path)
  task_attachments.is_result_doc  — flag: attached as proof of result
  company_attachments             — new table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "9aV_attachments"
down_revision: Union[str, None] = "9aU_task_project_result_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extend task_attachments
    op.add_column("task_attachments",
        sa.Column("storage_key", sa.String(1024), nullable=True))
    op.add_column("task_attachments",
        sa.Column("is_result_doc", sa.Boolean, nullable=False, server_default=sa.false()))

    # Project attachments — separate table (FK to projects)
    op.create_table("project_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("uploader_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("is_result_doc", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Company-level documents (org-wide, not task-tied)
    op.create_table("company_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("uploader_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),  # contracts | reports | legal | other
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("size_bytes", sa.Integer, nullable=True),
        sa.Column("year", sa.Integer, nullable=True, index=True),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_company_attachments_company_category", "company_attachments", ["company_id", "category"])


def downgrade() -> None:
    op.drop_index("ix_company_attachments_company_category", table_name="company_attachments")
    op.drop_table("company_attachments")
    op.drop_table("project_attachments")
    op.drop_column("task_attachments", "is_result_doc")
    op.drop_column("task_attachments", "storage_key")
