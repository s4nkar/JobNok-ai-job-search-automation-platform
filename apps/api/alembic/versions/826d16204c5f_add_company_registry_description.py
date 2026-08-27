"""add company_registry description

Revision ID: 826d16204c5f
Revises: e64a6643c9a0
Create Date: 2026-08-27 19:29:16.745873

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '826d16204c5f'
down_revision: Union[str, None] = 'e64a6643c9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only company_registry.description - autogenerate also proposed
    # dropping/recreating jobs_source_job_id_key as an unrelated pre-existing
    # index-vs-constraint drift, not part of this change.
    op.add_column('company_registry', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('company_registry', 'description')
