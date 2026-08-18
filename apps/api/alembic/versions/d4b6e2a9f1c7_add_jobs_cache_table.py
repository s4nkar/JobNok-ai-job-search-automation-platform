"""add jobs cache table and job_search_applications.job_id fk

Revision ID: d4b6e2a9f1c7
Revises: c1d5f8a3e7b2
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4b6e2a9f1c7'
down_revision: Union[str, None] = 'c1d5f8a3e7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        # Shared/global cache row — no user_id, every user's search shares the same record.
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('source_job_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('company', sa.Text(), nullable=False),
        sa.Column('location', sa.Text(), nullable=False),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('salary_min', sa.Numeric(), nullable=True),
        sa.Column('salary_max', sa.Numeric(), nullable=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('apply_url', sa.Text(), nullable=False),
        sa.Column('canonical_url', sa.Text(), nullable=False),
        sa.Column('posted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('fetched_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_seen_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('jobs_source_job_id_key', 'jobs', ['source', 'source_job_id'], unique=True)
    op.create_index('jobs_canonical_url_idx', 'jobs', ['canonical_url'])
    op.create_index('jobs_expires_at_idx', 'jobs', ['expires_at'])

    op.add_column(
        'job_search_applications',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'job_search_applications_job_id_fkey',
        'job_search_applications', 'jobs',
        ['job_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('job_search_applications_job_id_fkey', 'job_search_applications', type_='foreignkey')
    op.drop_column('job_search_applications', 'job_id')

    op.drop_index('jobs_expires_at_idx', table_name='jobs')
    op.drop_index('jobs_canonical_url_idx', table_name='jobs')
    op.drop_index('jobs_source_job_id_key', table_name='jobs')
    op.drop_table('jobs')
