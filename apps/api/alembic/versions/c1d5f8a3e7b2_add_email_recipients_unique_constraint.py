"""add unique constraint on email_recipients(campaign_id, email)

Revision ID: c1d5f8a3e7b2
Revises: a7c4e91f2b6d
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c1d5f8a3e7b2'
down_revision: Union[str, None] = 'a7c4e91f2b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'email_recipients_campaign_id_email_key',
        'email_recipients',
        ['campaign_id', 'email'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'email_recipients_campaign_id_email_key',
        'email_recipients',
        type_='unique',
    )
