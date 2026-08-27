"""add jobs.company_id and startup_hunt_companies.registry_company_id fks to company_registry

Revision ID: c7d1f4a8e356
Revises: b2e6a9c4f108
Create Date: 2026-08-24 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7d1f4a8e356'
down_revision: Union[str, None] = 'b2e6a9c4f108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'jobs',
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'jobs_company_id_fkey',
        'jobs', 'company_registry',
        ['company_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('jobs_company_id_idx', 'jobs', ['company_id'])

    op.add_column(
        'startup_hunt_companies',
        sa.Column('registry_company_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'startup_hunt_companies_registry_company_id_fkey',
        'startup_hunt_companies', 'company_registry',
        ['registry_company_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'startup_hunt_companies_registry_company_id_fkey', 'startup_hunt_companies', type_='foreignkey'
    )
    op.drop_column('startup_hunt_companies', 'registry_company_id')

    op.drop_index('jobs_company_id_idx', table_name='jobs')
    op.drop_constraint('jobs_company_id_fkey', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'company_id')
