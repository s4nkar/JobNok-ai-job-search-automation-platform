"""add source_job_application_id to tailoring/cover_letter/interview_prep sessions

Third linkage column alongside the existing source_opportunity_id (Startup
Hunt leads) and source_application_id (synced Job Search rows) - lets My
Docs group documents generated from a manually-added tracker Application
row too, which previously had no FK thread into doc generation at all.

Revision ID: c2e5f9b7a814
Revises: b1f4d8a0c6e3
Create Date: 2026-11-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c2e5f9b7a814'
down_revision: Union[str, None] = 'b1f4d8a0c6e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ('tailoring_sessions', 'cover_letter_sessions', 'interview_prep_sessions')


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column('source_job_application_id', postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f'{table}_source_job_application_id_fkey',
            table, 'job_applications',
            ['source_job_application_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_constraint(f'{table}_source_job_application_id_fkey', table, type_='foreignkey')
        op.drop_column(table, 'source_job_application_id')
