"""add tailoring_sessions draft_cv_data column

Revision ID: 9b3f0d6a1c84
Revises: d7e19a4c3b52
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9b3f0d6a1c84'
down_revision: Union[str, None] = 'd7e19a4c3b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tailoring_sessions',
        sa.Column('draft_cv_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tailoring_sessions', 'draft_cv_data')
