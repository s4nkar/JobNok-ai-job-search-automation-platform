"""add pg_trgm gin indexes on company_registry.city and .country

Revision ID: 524f297bbadf
Revises: a1f5c9e3b7d2
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '524f297bbadf'
down_revision: Union[str, None] = 'a1f5c9e3b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # startup_scout/service.py::_company_registry_candidates filters with
    # ILIKE '%token%' on city/country - same leading-wildcard problem as
    # jobs.title/description (see a22ae866fa45): a plain B-tree index can't
    # be used at all for this pattern, so without this every DB-first
    # candidate lookup is a full table scan (confirmed via EXPLAIN: Seq Scan,
    # 672 rows today - cheap now, not once the crawler keeps growing this
    # table). pg_trgm is already installed (a22ae866fa45), just extending it
    # to these two columns.
    op.execute(
        'CREATE INDEX company_registry_city_trgm_idx ON company_registry USING gin (city gin_trgm_ops)'
    )
    op.execute(
        'CREATE INDEX company_registry_country_trgm_idx ON company_registry USING gin (country gin_trgm_ops)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS company_registry_country_trgm_idx')
    op.execute('DROP INDEX IF EXISTS company_registry_city_trgm_idx')
