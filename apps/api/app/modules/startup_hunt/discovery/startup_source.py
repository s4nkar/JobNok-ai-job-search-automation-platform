"""Provider-agnostic startup discovery abstraction (PRD section 10) - adding
a new discovery source (YC, EU Startups, an accelerator's portfolio page,
...) should only ever mean writing a new class here, never touching
discovery_service.py or the workers that consume it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class DiscoveredStartup:
    name: str
    domain: str | None
    website_url: str | None
    country: str | None
    city: str | None
    discovery_source: str
    discovery_source_url: str | None
    discovery_source_id: str | None


class StartupSource(Protocol):
    """Anything with an async discover() returning a batch of startups can be
    plugged into discovery_service.py - see startupmap.py for the reference
    implementation.

    Only discover()'s own signature is part of this contract - a concrete
    source's __init__ is free to take whatever it needs for its own
    dedup/pagination strategy (e.g. StartupMapSource takes a set of
    already-known ids to sample around, since it has no natural paging
    cursor of its own; a future paginated-API source might instead take a
    `since` cursor). The worker that owns each source's DB access (see
    workers/discovery_worker.py) is responsible for supplying whatever that
    particular source asks for before calling discover().
    """

    async def discover(self) -> list[DiscoveredStartup]: ...
