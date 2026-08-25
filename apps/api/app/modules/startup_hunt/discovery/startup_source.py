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
    implementation."""

    async def discover(self) -> list[DiscoveredStartup]: ...
