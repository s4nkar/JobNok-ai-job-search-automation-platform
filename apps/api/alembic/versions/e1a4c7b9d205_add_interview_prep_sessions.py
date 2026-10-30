"""add interview_prep_sessions table

Revision ID: e1a4c7b9d205
Revises: d9f2a4e6b8c1
Create Date: 2026-10-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1a4c7b9d205'
down_revision: Union[str, None] = 'd9f2a4e6b8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'interview_prep_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_description', sa.Text(), nullable=False),
        sa.Column('company', sa.Text(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('source_opportunity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_application_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("char_length(job_description) <= 12000", name='interview_prep_sessions_jd_length_check'),
        sa.CheckConstraint("company is null or char_length(company) <= 200", name='interview_prep_sessions_company_length_check'),
        sa.CheckConstraint("role is null or char_length(role) <= 200", name='interview_prep_sessions_role_length_check'),
        sa.CheckConstraint("title is null or char_length(title) <= 200", name='interview_prep_sessions_title_length_check'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_opportunity_id'], ['startup_hunt_opportunities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_application_id'], ['job_search_applications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'interview_prep_sessions_user_id_idx', 'interview_prep_sessions', ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('interview_prep_sessions_user_id_idx', table_name='interview_prep_sessions')
    op.drop_table('interview_prep_sessions')
