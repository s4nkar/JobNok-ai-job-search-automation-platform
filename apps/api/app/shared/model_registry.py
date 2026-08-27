"""Imports every module's models.py so all tables register on Base.metadata.

Import this once — from app/main.py and alembic/env.py — before anything that
relies on FK resolution across module boundaries (SQLAlchemy's table sort on
flush/create) or on Base.metadata being fully populated (Alembic autogenerate).
Without this, a module whose queries haven't been migrated to SQLAlchemy yet
never gets its models.py imported anywhere, so any *other* module's FK
pointing at its table fails with NoReferencedTableError at flush time.
"""

from app.modules.profile.models import Profile  # noqa: F401
from app.modules.templates.models import Template  # noqa: F401
from app.modules.bulk_email.models import EmailCampaign, EmailRecipient  # noqa: F401
from app.modules.tracker.models import JobApplication  # noqa: F401
from app.modules.job_search.models import JobSearchApplication  # noqa: F401
from app.modules.startup_hunt.models import (  # noqa: F401
    StartupHuntCompany,
    StartupHuntOpportunity,
    StartupHuntContact,
    OpportunityArtifact,
    StartupHuntSource,
    CompanyRegistry,
)
from app.modules.startup_scout.models import StartupScoutCompany, StartupScoutContact  # noqa: F401
from app.modules.linkedin_fill.models import LinkedinCache  # noqa: F401
from app.modules.usage.models import ToolUsageEvent  # noqa: F401
