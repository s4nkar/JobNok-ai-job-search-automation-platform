"""add jobs.origin_tool column and country/posted_at index

Revision ID: e2f7c9a4b8d1
Revises: d4b6e2a9f1c7
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f7c9a4b8d1'
down_revision: Union[str, None] = 'd4b6e2a9f1c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'jobs',
        sa.Column('origin_tool', sa.Text(), nullable=False, server_default='recent_job_search'),
    )
    op.create_index(
        'jobs_country_posted_at_idx',
        'jobs',
        ['country', sa.text('posted_at DESC')],
    )


def downgrade() -> None:
    op.drop_index('jobs_country_posted_at_idx', table_name='jobs')
    op.drop_column('jobs', 'origin_tool')
