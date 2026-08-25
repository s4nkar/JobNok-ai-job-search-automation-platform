"""Shared exponential backoff schedule (PRD section 34) - used by both
sync_worker.py (a company whose job sync keeps failing) and
scheduler.py's stuck-resolution sweep (a company whose resolution keeps
getting stuck/failing). One schedule, one place, so the two don't drift.
"""

from __future__ import annotations

# Capped at 48h. Indexed by min(consecutive_failures - 1, len - 1).
_BACKOFF_HOURS = (1, 2, 4, 8, 24, 48)


def backoff_hours(consecutive_failures: int) -> int:
    index = min(max(consecutive_failures - 1, 0), len(_BACKOFF_HOURS) - 1)
    return _BACKOFF_HOURS[index]
