"""add funding_stage and employee_count_min/max to company_registry

Revision ID: e64a6643c9a0
Revises: 524f297bbadf
Create Date: 2026-08-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e64a6643c9a0'
down_revision: Union[str, None] = '524f297bbadf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Neither the crawler (StartupMap) nor startup_scout (DDG) had anywhere
    # to store funding stage / team size before this, even though both
    # already extract it - see app/shared/funding_stages.py and
    # discovery/startupmap.py for where it's read from. Nullable: the
    # ~900 existing rows won't have this until either re-discovered or
    # backfilled (see workers/backfill_company_metadata.py).
    op.add_column('company_registry', sa.Column('funding_stage', sa.Text(), nullable=True))
    op.add_column('company_registry', sa.Column('employee_count_min', sa.Integer(), nullable=True))
    op.add_column('company_registry', sa.Column('employee_count_max', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('company_registry', 'employee_count_max')
    op.drop_column('company_registry', 'employee_count_min')
    op.drop_column('company_registry', 'funding_stage')
