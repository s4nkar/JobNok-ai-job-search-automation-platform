"""add original_pdf_bytes and original_pdf_uploaded_at to resume_versions

Revision ID: c7f4a2d81e6b
Revises: a5e21f8b93d4
Create Date: 2026-09-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c7f4a2d81e6b'
down_revision: Union[str, None] = 'a5e21f8b93d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('resume_versions', sa.Column('original_pdf_bytes', sa.LargeBinary(), nullable=True))
    op.add_column('resume_versions', sa.Column('original_pdf_uploaded_at', sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('resume_versions', 'original_pdf_uploaded_at')
    op.drop_column('resume_versions', 'original_pdf_bytes')
