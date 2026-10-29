"""add cover_letter_sessions table

Revision ID: d9f2a4e6b8c1
Revises: c8e2f7a4d103
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd9f2a4e6b8c1'
down_revision: Union[str, None] = 'c8e2f7a4d103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cover_letter_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('selling_points', sa.Text(), nullable=False),
        sa.Column('resume_text', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('source_opportunity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_application_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("char_length(company) <= 200", name='cover_letter_sessions_company_length_check'),
        sa.CheckConstraint("char_length(role) <= 200", name='cover_letter_sessions_role_length_check'),
        sa.CheckConstraint("char_length(selling_points) <= 3000", name='cover_letter_sessions_selling_points_length_check'),
        sa.CheckConstraint("char_length(content) <= 5000", name='cover_letter_sessions_content_length_check'),
        sa.CheckConstraint("title is null or char_length(title) <= 200", name='cover_letter_sessions_title_length_check'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_opportunity_id'], ['startup_hunt_opportunities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_application_id'], ['job_search_applications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'cover_letter_sessions_user_id_idx', 'cover_letter_sessions', ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('cover_letter_sessions_user_id_idx', table_name='cover_letter_sessions')
    op.drop_table('cover_letter_sessions')
