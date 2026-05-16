"""Project editor: ground_type, project_type, linked_project_id + project_comments

Revision ID: 7c29bd804fae
Revises: 0023_consultants
Create Date: 20260508-112329
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '7c29bd804fae'
down_revision = '0023_consultants'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('ground_type', sa.String(32), nullable=True))
    op.create_index('ix_projects_ground_type', 'projects', ['ground_type'])

    op.add_column('projects', sa.Column('project_type', sa.String(32), nullable=True, server_default='onetime'))
    op.create_index('ix_projects_project_type', 'projects', ['project_type'])

    op.add_column('projects', sa.Column('linked_project_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_projects_linked_project_id',
        'projects', 'projects',
        ['linked_project_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_projects_linked_project_id', 'projects', ['linked_project_id'])

    op.create_table(
        'project_comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_edited', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_project_comments_project_id', 'project_comments', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_project_comments_project_id', table_name='project_comments')
    op.drop_table('project_comments')

    op.drop_index('ix_projects_linked_project_id', table_name='projects')
    op.drop_constraint('fk_projects_linked_project_id', 'projects', type_='foreignkey')
    op.drop_column('projects', 'linked_project_id')

    op.drop_index('ix_projects_project_type', table_name='projects')
    op.drop_column('projects', 'project_type')

    op.drop_index('ix_projects_ground_type', table_name='projects')
    op.drop_column('projects', 'ground_type')