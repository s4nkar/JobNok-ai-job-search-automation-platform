"""add job_applications length and status check constraints

Revision ID: a3c7e9f1b5d2
Revises: f4b8d1c9e3a7
Create Date: 2026-11-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3c7e9f1b5d2'
down_revision: Union[str, None] = 'f4b8d1c9e3a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint('applications_company_length_check', 'job_applications', 'char_length(company) <= 200')
    op.create_check_constraint('applications_role_length_check', 'job_applications', 'char_length(role) <= 200')
    op.create_check_constraint(
        'applications_notes_length_check', 'job_applications', 'notes is null or char_length(notes) <= 3000',
    )
    op.create_check_constraint(
        'applications_status_check', 'job_applications',
        "status in ('Applied', 'Phone Screen', 'Interview', 'Offer', 'Rejected', 'Withdrawn')",
    )


def downgrade() -> None:
    op.drop_constraint('applications_status_check', 'job_applications', type_='check')
    op.drop_constraint('applications_notes_length_check', 'job_applications', type_='check')
    op.drop_constraint('applications_role_length_check', 'job_applications', type_='check')
    op.drop_constraint('applications_company_length_check', 'job_applications', type_='check')
