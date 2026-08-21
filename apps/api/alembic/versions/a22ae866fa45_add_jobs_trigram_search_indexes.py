"""add pg_trgm gin indexes on jobs.title and jobs.description

Revision ID: a22ae866fa45
Revises: b11c589bd437
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a22ae866fa45'
down_revision: Union[str, None] = 'b11c589bd437'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # query_job_cache_candidates() filters with ILIKE '%token%' on title/description
    # - a leading-wildcard ILIKE can't use a plain B-tree index at all, so without
    # this every DB-first cache lookup is a full table scan once `jobs` has real
    # volume. gin_trgm_ops lets ILIKE '%...%' use a GIN index instead.
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute(
        'CREATE INDEX jobs_title_trgm_idx ON jobs USING gin (title gin_trgm_ops)'
    )
    op.execute(
        'CREATE INDEX jobs_description_trgm_idx ON jobs USING gin (description gin_trgm_ops)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS jobs_description_trgm_idx')
    op.execute('DROP INDEX IF EXISTS jobs_title_trgm_idx')
