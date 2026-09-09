"""drop resume_versions.original_pdf_bytes/original_pdf_uploaded_at

Superseded by saved_resumes (see d3e8f5a2b7c1) — "compare with original" now
sources from a permanent saved resume instead of this 48h ephemeral cache, so
these columns (and their ARQ sweep, removed in the same change) are no longer
read or written anywhere.

Revision ID: e6b1c4d9a3f7
Revises: d3e8f5a2b7c1
Create Date: 2026-09-08 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6b1c4d9a3f7'
down_revision: Union[str, None] = 'd3e8f5a2b7c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('resume_versions', 'original_pdf_uploaded_at')
    op.drop_column('resume_versions', 'original_pdf_bytes')


def downgrade() -> None:
    op.add_column('resume_versions', sa.Column('original_pdf_bytes', sa.LargeBinary(), nullable=True))
    op.add_column('resume_versions', sa.Column('original_pdf_uploaded_at', sa.TIMESTAMP(timezone=True), nullable=True))
