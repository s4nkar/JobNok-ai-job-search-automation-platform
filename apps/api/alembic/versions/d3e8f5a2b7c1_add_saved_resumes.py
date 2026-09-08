"""add saved_resumes table and tailoring_sessions.saved_resume_id

Revision ID: d3e8f5a2b7c1
Revises: c7f4a2d81e6b
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd3e8f5a2b7c1'
down_revision: Union[str, None] = 'c7f4a2d81e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_resumes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('cloudinary_public_id', sa.Text(), nullable=False),
        sa.Column('original_filename', sa.Text(), nullable=False),
        sa.Column('sha256', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('slot between 1 and 3', name='saved_resumes_slot_range_check'),
        sa.CheckConstraint('char_length(label) <= 100', name='saved_resumes_label_length_check'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'slot', name='saved_resumes_user_id_slot_key'),
    )
    op.add_column(
        'tailoring_sessions',
        sa.Column('saved_resume_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'tailoring_sessions_saved_resume_id_fkey', 'tailoring_sessions', 'saved_resumes',
        ['saved_resume_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('tailoring_sessions_saved_resume_id_fkey', 'tailoring_sessions', type_='foreignkey')
    op.drop_column('tailoring_sessions', 'saved_resume_id')
    op.drop_table('saved_resumes')
