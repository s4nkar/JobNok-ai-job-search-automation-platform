"""add templates length and category check constraints

Revision ID: f4b8d1c9e3a7
Revises: e1a4c7b9d205
Create Date: 2026-10-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f4b8d1c9e3a7'
down_revision: Union[str, None] = 'e1a4c7b9d205'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint('templates_name_length_check', 'templates', 'char_length(name) <= 100')
    op.create_check_constraint('templates_content_length_check', 'templates', 'char_length(content) <= 5000')
    op.create_check_constraint(
        'templates_category_check', 'templates',
        "category in ('Cold DM - Recruiter', 'Cold DM - Hiring Manager', 'Follow-Up', 'Referral Ask', 'Email Outreach', 'Custom')",
    )


def downgrade() -> None:
    op.drop_constraint('templates_category_check', 'templates', type_='check')
    op.drop_constraint('templates_content_length_check', 'templates', type_='check')
    op.drop_constraint('templates_name_length_check', 'templates', type_='check')
