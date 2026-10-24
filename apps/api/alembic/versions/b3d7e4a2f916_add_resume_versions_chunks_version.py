"""add chunks_version to resume_versions

Revision ID: b3d7e4a2f916
Revises: f2a9c6e1d4b8
Create Date: 2026-10-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b3d7e4a2f916'
down_revision: Union[str, None] = 'f2a9c6e1d4b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('resume_versions', sa.Column('chunks_version', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('resume_versions', 'chunks_version')
