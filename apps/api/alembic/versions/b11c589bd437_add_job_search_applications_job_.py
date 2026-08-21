"""add job_search_applications.job_description

Revision ID: b11c589bd437
Revises: f1a3c8d5e2b7
Create Date: 2026-08-19 23:30:26.945010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b11c589bd437'
down_revision: Union[str, None] = 'f1a3c8d5e2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'job_search_applications',
        sa.Column('job_description', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('job_search_applications', 'job_description')
