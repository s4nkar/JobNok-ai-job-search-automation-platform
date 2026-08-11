"""add tool_usage_events

Revision ID: f3a9d7c2e1b4
Revises: b8c8fffadcd0
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3a9d7c2e1b4'
down_revision: Union[str, None] = 'b8c8fffadcd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tool_usage_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool_slug', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('tool_usage_events_user_id_idx', 'tool_usage_events', ['user_id'])
    op.create_index('tool_usage_events_user_tool_idx', 'tool_usage_events', ['user_id', 'tool_slug'])
    op.create_index('tool_usage_events_user_created_idx', 'tool_usage_events', ['user_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('tool_usage_events_user_created_idx', table_name='tool_usage_events')
    op.drop_index('tool_usage_events_user_tool_idx', table_name='tool_usage_events')
    op.drop_index('tool_usage_events_user_id_idx', table_name='tool_usage_events')
    op.drop_table('tool_usage_events')
