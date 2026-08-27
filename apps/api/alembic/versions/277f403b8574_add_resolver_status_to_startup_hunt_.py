"""add resolver status to startup hunt sources

Revision ID: 277f403b8574
Revises: a22ae866fa45
Create Date: 2026-08-22 04:07:00.224902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '277f403b8574'
down_revision: Union[str, None] = 'a22ae866fa45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: autogenerate also proposed dropping/recreating jobs_source_job_id_key
    # (index -> constraint) - unrelated pre-existing drift between how that
    # unique key was originally created and how the ORM declares it today,
    # not something this migration touches. Left out deliberately.
    op.add_column('startup_hunt_sources', sa.Column('status', sa.Text(), server_default='resolved', nullable=False))
    op.add_column('startup_hunt_sources', sa.Column('resolution_error', sa.Text(), nullable=True))
    op.alter_column('startup_hunt_sources', 'type',
               existing_type=sa.TEXT(),
               nullable=True)
    op.create_index('startup_hunt_sources_name_idx', 'startup_hunt_sources', ['name'], unique=False)
    op.create_index('startup_hunt_sources_status_idx', 'startup_hunt_sources', ['status'], unique=False)
    op.create_check_constraint(
        'startup_hunt_sources_status_check',
        'startup_hunt_sources',
        "status in ('resolved', 'pending', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint('startup_hunt_sources_status_check', 'startup_hunt_sources', type_='check')
    op.drop_index('startup_hunt_sources_status_idx', table_name='startup_hunt_sources')
    op.drop_index('startup_hunt_sources_name_idx', table_name='startup_hunt_sources')
    op.alter_column('startup_hunt_sources', 'type',
               existing_type=sa.TEXT(),
               nullable=False)
    op.drop_column('startup_hunt_sources', 'resolution_error')
    op.drop_column('startup_hunt_sources', 'status')
