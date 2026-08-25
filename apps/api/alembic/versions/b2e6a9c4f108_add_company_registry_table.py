"""add company_registry table

Revision ID: b2e6a9c4f108
Revises: 277f403b8574
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2e6a9c4f108'
down_revision: Union[str, None] = '277f403b8574'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Global, deduplicated registry of startups discovered by the background
    # crawler pipeline - no user_id, one row per real-world company, never
    # per-user. See app/modules/startup_hunt/models.py::CompanyRegistry.
    op.create_table(
        'company_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('normalized_name', sa.Text(), nullable=False),
        sa.Column('domain', sa.Text(), nullable=True),
        sa.Column('website_url', sa.Text(), nullable=True),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('city', sa.Text(), nullable=True),
        sa.Column('discovery_source', sa.Text(), nullable=False),
        sa.Column('discovery_source_url', sa.Text(), nullable=True),
        sa.Column('discovery_source_id', sa.Text(), nullable=True),
        sa.Column('career_url', sa.Text(), nullable=True),
        sa.Column('ats_provider', sa.Text(), nullable=True),
        sa.Column('ats_identifier', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), server_default='discovered', nullable=False),
        sa.Column('crawl_frequency_hours', sa.Integer(), server_default='48', nullable=False),
        sa.Column('crawl_priority', sa.Text(), server_default='normal', nullable=False),
        sa.Column('last_discovered_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_resolved_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_synced_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('next_crawl_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_job_found_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_job_change_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status in ('discovered', 'resolving', 'resolved', 'active', "
            "'no_careers_page', 'no_jobs', 'failed', 'disabled')",
            name='company_registry_status_check',
        ),
        sa.CheckConstraint(
            "crawl_priority in ('high', 'normal', 'low')",
            name='company_registry_crawl_priority_check',
        ),
    )
    # Partial unique indexes, not table-level UNIQUE constraints - both dedup
    # keys (domain, discovery_source+discovery_source_id) are optional, a row
    # can start life with neither set.
    op.create_index(
        'company_registry_domain_key', 'company_registry', ['domain'],
        unique=True, postgresql_where=sa.text('domain IS NOT NULL'),
    )
    op.create_index(
        'company_registry_discovery_source_id_key', 'company_registry',
        ['discovery_source', 'discovery_source_id'],
        unique=True, postgresql_where=sa.text('discovery_source_id IS NOT NULL'),
    )
    op.create_index('company_registry_normalized_name_idx', 'company_registry', ['normalized_name'])
    op.create_index('company_registry_status_idx', 'company_registry', ['status'])
    op.create_index(
        'company_registry_next_crawl_idx', 'company_registry', ['next_crawl_at'],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index('company_registry_next_crawl_idx', table_name='company_registry')
    op.drop_index('company_registry_status_idx', table_name='company_registry')
    op.drop_index('company_registry_normalized_name_idx', table_name='company_registry')
    op.drop_index('company_registry_discovery_source_id_key', table_name='company_registry')
    op.drop_index('company_registry_domain_key', table_name='company_registry')
    op.drop_table('company_registry')
