"""drop opportunity_artifacts table

Superseded by the per-tool session tables (tailoring_sessions,
cover_letter_sessions, interview_prep_sessions) that My Docs now reads from.
opportunity_artifacts was a separate, Startup Hunt-only artifact log that
powered the inline "Docs" panel on the tracker's Leads tab - with that panel
removed, nothing reads this table anymore.

Revision ID: b1f4d8a0c6e3
Revises: a3c7e9f1b5d2
Create Date: 2026-11-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1f4d8a0c6e3'
down_revision: Union[str, None] = 'a3c7e9f1b5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('opportunity_artifacts_user_idx', table_name='opportunity_artifacts')
    op.drop_index('opportunity_artifacts_opportunity_idx', table_name='opportunity_artifacts')
    op.drop_table('opportunity_artifacts')


def downgrade() -> None:
    op.create_table(
        'opportunity_artifacts',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('opportunity_id', sa.UUID(), nullable=True),
        sa.Column('artifact_type', sa.Text(), nullable=False),
        sa.Column('tool_used', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "artifact_type in ('resume_analysis', 'cover_letter', 'interview_prep')",
            name='opportunity_artifact_type_check',
        ),
        sa.ForeignKeyConstraint(['opportunity_id'], ['startup_hunt_opportunities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('opportunity_artifacts_opportunity_idx', 'opportunity_artifacts', ['opportunity_id'], unique=False)
    op.create_index('opportunity_artifacts_user_idx', 'opportunity_artifacts', ['user_id'], unique=False)
