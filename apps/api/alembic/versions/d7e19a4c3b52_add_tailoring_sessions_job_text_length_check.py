"""add tailoring_sessions job_text length check constraint

Revision ID: d7e19a4c3b52
Revises: c4f8b21e6a9d
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd7e19a4c3b52'
down_revision: Union[str, None] = 'c4f8b21e6a9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        'tailoring_sessions_job_text_length_check', 'tailoring_sessions',
        'char_length(job_text) <= 20000',
    )


def downgrade() -> None:
    op.drop_constraint('tailoring_sessions_job_text_length_check', 'tailoring_sessions', type_='check')
