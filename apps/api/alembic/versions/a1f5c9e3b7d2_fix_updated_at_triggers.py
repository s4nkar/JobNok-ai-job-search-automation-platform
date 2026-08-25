"""fix missing company_registry updated_at trigger, add email_recipients updated_at

Revision ID: a1f5c9e3b7d2
Revises: c7d1f4a8e356
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f5c9e3b7d2'
down_revision: Union[str, None] = 'c7d1f4a8e356'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Bugfix: company_registry's `updated_at` column was created (see
    # b2e6a9c4f108) with the model docstring already claiming it was
    # trigger-managed, but the trigger itself was never actually attached -
    # the column would have silently frozen at each row's insert time. Fixes
    # that, and adds the same column + trigger to email_recipients, which
    # never had an updated_at column at all - both are needed for their
    # respective stuck-job sweeps (see startup_hunt/ingestion/scheduler.py
    # and bulk_email/tasks.py) to detect staleness.
    op.add_column(
        'email_recipients',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    for table in ('company_registry', 'email_recipients'):
        op.execute(f"""
            create trigger {table}_updated_at
              before update on public.{table}
              for each row execute procedure public.set_updated_at();
        """)


def downgrade() -> None:
    for table in ('company_registry', 'email_recipients'):
        op.execute(f"drop trigger if exists {table}_updated_at on public.{table}")
    op.drop_column('email_recipients', 'updated_at')
