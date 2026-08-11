"""add startup_hunt_sources table

Revision ID: a7c4e91f2b6d
Revises: f3a9d7c2e1b4
Create Date: 2026-08-11 00:00:00.000000

"""
import json
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a7c4e91f2b6d'
down_revision: Union[str, None] = 'f3a9d7c2e1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app/modules/startup_hunt/engine.py's ALLOWED_SOURCE_TYPES — duplicated
# here (not imported) so this migration keeps working unchanged even if that
# module's code moves or the set's definition changes later.
_ALLOWED_SOURCE_TYPES = {
    "greenhouse", "lever", "ashby", "startup_company", "startup_directory",
    "google_web", "web_search", "ats_discovery", "apify_actor", "indeed_search", "theirstack_search",
}


def upgrade() -> None:
    op.create_table(
        'startup_hunt_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        # NULL = globally curated source visible to every user; set = one user's own addition.
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('company', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=True),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('startup_hunt_sources_user_id_idx', 'startup_hunt_sources', ['user_id'])

    # One-time backfill: copy whatever STARTUP_HUNT_SOURCES_JSON held into global
    # (user_id NULL) rows, so the curated list this migration replaces isn't lost
    # on cutover. Reads the raw env var directly (not app.core.config.settings) so
    # this keeps working even after that field is removed from Settings.
    try:
        raw = json.loads(os.environ.get("STARTUP_HUNT_SOURCES_JSON", "[]"))
    except json.JSONDecodeError:
        raw = []

    rows_to_insert = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            source_type = str(item.get("type", "")).strip().lower()
            name = str(item.get("name", "")).strip()
            if not name or source_type not in _ALLOWED_SOURCE_TYPES:
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            rows_to_insert.append({
                "type": source_type,
                "name": name,
                "company": str(item.get("company", "")).strip() or name,
                "slug": str(item.get("slug", "")).strip() or None,
                "url": str(item.get("url", "")).strip() or None,
                "metadata": json.dumps(metadata),
                "user_id": None,
            })

    if rows_to_insert:
        source_table = sa.table(
            'startup_hunt_sources',
            sa.column('type', sa.Text),
            sa.column('name', sa.Text),
            sa.column('company', sa.Text),
            sa.column('slug', sa.Text),
            sa.column('url', sa.Text),
            sa.column('metadata', postgresql.JSONB),
            sa.column('user_id', postgresql.UUID),
        )
        op.bulk_insert(source_table, rows_to_insert)


def downgrade() -> None:
    op.drop_index('startup_hunt_sources_user_id_idx', table_name='startup_hunt_sources')
    op.drop_table('startup_hunt_sources')
