"""add key_selling_points to profiles

Revision ID: c8e2f7a4d103
Revises: b3d7e4a2f916
Create Date: 2026-10-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c8e2f7a4d103'
down_revision: Union[str, None] = 'b3d7e4a2f916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('profiles', sa.Column('key_selling_points', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('profiles', 'key_selling_points')
