"""add resume_tailor tables (resume_versions, tailoring_sessions)

Revision ID: c4f8b21e6a9d
Revises: 826d16204c5f
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4f8b21e6a9d'
down_revision: Union[str, None] = '826d16204c5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'resume_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sha256', sa.Text(), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('chunks', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('embeddings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('embeddings_model', sa.Text(), nullable=True),
        sa.Column('base_cv_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('base_cv_data_prompt_version', sa.Text(), nullable=True),
        sa.Column('last_used_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'sha256', name='resume_versions_user_id_sha256_key'),
    )

    op.create_table(
        'tailoring_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resume_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_hash', sa.Text(), nullable=False),
        sa.Column('job_text', sa.Text(), nullable=False),
        sa.Column('job_text_clean', sa.Text(), nullable=False),
        sa.Column('job_chunks', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('job_embeddings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('analysis', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('prose', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('matcher_version', sa.Text(), nullable=False),
        sa.Column('prompt_version', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default='ready', nullable=False),
        sa.Column('ai_status', sa.Text(), server_default='ok', nullable=False),
        sa.Column('ai_provider', sa.Text(), nullable=True),
        sa.Column('ai_error', sa.Text(), nullable=True),
        sa.Column('template_id', sa.Text(), nullable=True),
        sa.Column('source_opportunity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_application_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.CheckConstraint("status in ('ready', 'failed')", name='tailoring_sessions_status_check'),
        sa.CheckConstraint("ai_status in ('ok', 'degraded')", name='tailoring_sessions_ai_status_check'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resume_version_id'], ['resume_versions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_opportunity_id'], ['startup_hunt_opportunities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_application_id'], ['job_search_applications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'tailoring_sessions_user_resume_job_idx', 'tailoring_sessions',
        ['user_id', 'resume_version_id', 'job_hash'],
    )


def downgrade() -> None:
    op.drop_index('tailoring_sessions_user_resume_job_idx', table_name='tailoring_sessions')
    op.drop_table('tailoring_sessions')
    op.drop_table('resume_versions')
