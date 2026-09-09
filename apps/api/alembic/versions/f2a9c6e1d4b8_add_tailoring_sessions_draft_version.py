"""add tailoring_sessions.draft_version

Powers optimistic concurrency on PATCH /tailor/{id}/draft — see models.py's
TailoringSession.draft_version docstring.

Revision ID: f2a9c6e1d4b8
Revises: e6b1c4d9a3f7
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a9c6e1d4b8'
down_revision: Union[str, None] = 'e6b1c4d9a3f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tailoring_sessions',
        sa.Column('draft_version', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('tailoring_sessions', 'draft_version')
