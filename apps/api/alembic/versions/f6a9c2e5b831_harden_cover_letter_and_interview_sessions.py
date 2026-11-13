"""harden cover_letter_sessions and interview_prep_sessions

Two production-audit fixes for the "My Docs" session tables:

1. cover_letter_sessions.resume_text had a Pydantic max_length=8000 boundary
   (CoverLetterRequest.resume_text, schemas.py) but no matching DB CHECK -
   every other text column on this table has one; this closes that gap.

2. Partial unique indexes on (user_id, source_opportunity_id) /
   (user_id, source_application_id) / (user_id, source_job_application_id)
   for both cover_letter_sessions and interview_prep_sessions. Each
   module's resolve_session() does a check-then-act upsert ("one saved
   session per job") with no DB-level barrier against two concurrent
   requests for the same job both missing the SELECT and both INSERTing -
   the per-user Redis single-flight lock in routes.py narrows this but
   fails open if Redis is unreachable. These indexes make the invariant
   real at the DB layer; service.py now catches the resulting
   IntegrityError and falls back to updating the row that won the race.

Revision ID: f6a9c2e5b831
Revises: c2e5f9b7a814
Create Date: 2026-11-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a9c2e5b831'
down_revision: Union[str, None] = 'c2e5f9b7a814'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        'cover_letter_sessions_resume_text_length_check',
        'cover_letter_sessions',
        'resume_text is null or char_length(resume_text) <= 8000',
    )

    op.create_index(
        'cover_letter_sessions_user_opportunity_key', 'cover_letter_sessions',
        ['user_id', 'source_opportunity_id'], unique=True,
        postgresql_where=sa.text('source_opportunity_id IS NOT NULL'),
    )
    op.create_index(
        'cover_letter_sessions_user_application_key', 'cover_letter_sessions',
        ['user_id', 'source_application_id'], unique=True,
        postgresql_where=sa.text('source_application_id IS NOT NULL'),
    )
    op.create_index(
        'cover_letter_sessions_user_job_application_key', 'cover_letter_sessions',
        ['user_id', 'source_job_application_id'], unique=True,
        postgresql_where=sa.text('source_job_application_id IS NOT NULL'),
    )

    op.create_index(
        'interview_prep_sessions_user_opportunity_key', 'interview_prep_sessions',
        ['user_id', 'source_opportunity_id'], unique=True,
        postgresql_where=sa.text('source_opportunity_id IS NOT NULL'),
    )
    op.create_index(
        'interview_prep_sessions_user_application_key', 'interview_prep_sessions',
        ['user_id', 'source_application_id'], unique=True,
        postgresql_where=sa.text('source_application_id IS NOT NULL'),
    )
    op.create_index(
        'interview_prep_sessions_user_job_application_key', 'interview_prep_sessions',
        ['user_id', 'source_job_application_id'], unique=True,
        postgresql_where=sa.text('source_job_application_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('interview_prep_sessions_user_job_application_key', table_name='interview_prep_sessions')
    op.drop_index('interview_prep_sessions_user_application_key', table_name='interview_prep_sessions')
    op.drop_index('interview_prep_sessions_user_opportunity_key', table_name='interview_prep_sessions')

    op.drop_index('cover_letter_sessions_user_job_application_key', table_name='cover_letter_sessions')
    op.drop_index('cover_letter_sessions_user_application_key', table_name='cover_letter_sessions')
    op.drop_index('cover_letter_sessions_user_opportunity_key', table_name='cover_letter_sessions')

    op.drop_constraint('cover_letter_sessions_resume_text_length_check', 'cover_letter_sessions', type_='check')
