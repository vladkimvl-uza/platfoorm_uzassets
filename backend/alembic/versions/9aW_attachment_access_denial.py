"""attachment_access_denial: admin per-user hide for files (Pack 150)

Allows admins to hide individual files (task/project/company attachments)
from specific users. The LIST endpoint filters denied rows out for the
requesting user; URL/delete endpoints return 403 for denied access.

Schema:
  attachment_access_denial
    id, kind ('task' | 'project' | 'company'), attachment_id (UUID),
    user_id, denied_by, denied_at, reason (optional)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "9aW_attachment_access_denial"
down_revision: Union[str, None] = "9aV_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachment_access_denial",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(16), nullable=False),         # task | project | company
        sa.Column("attachment_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("denied_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("denied_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("reason", sa.Text, nullable=True),
        sa.UniqueConstraint("kind", "attachment_id", "user_id",
                            name="uq_aad_kind_att_user"),
    )
    op.create_index("ix_aad_user", "attachment_access_denial", ["user_id"])
    op.create_index("ix_aad_kind_att",
                    "attachment_access_denial", ["kind", "attachment_id"])


def downgrade() -> None:
    op.drop_index("ix_aad_kind_att", table_name="attachment_access_denial")
    op.drop_index("ix_aad_user", table_name="attachment_access_denial")
    op.drop_table("attachment_access_denial")
