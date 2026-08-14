"""add startup_hunt_opportunities.job_id fk to jobs

Revision ID: f1a3c8d5e2b7
Revises: e2f7c9a4b8d1
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f1a3c8d5e2b7'
down_revision: Union[str, None] = 'e2f7c9a4b8d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'startup_hunt_opportunities',
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'startup_hunt_opportunities_job_id_fkey',
        'startup_hunt_opportunities', 'jobs',
        ['job_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('startup_hunt_opportunities_job_id_fkey', 'startup_hunt_opportunities', type_='foreignkey')
    op.drop_column('startup_hunt_opportunities', 'job_id')
