"""SSRF-safe URL fetching for the generic career-page crawler (and StartupMap
discovery, once enabled) - both fetch arbitrary third-party URLs by domain/
career_url, unlike every other provider in this module, which only ever
calls a small, hardcoded set of trusted API hosts (Ashby/Greenhouse/Lever/
TheirStack). See docs/startup_hunt/startup_hunt_crawler_prd.md section 40.

There is no existing reusable SSRF guard anywhere in this codebase - the
only related code (resume_tailor/routes.py::_safe_photo_url) is a hostname
regex that never resolves DNS, so it's bypassable via DNS rebinding, and
isn't exported. This is a new, real one: resolves the hostname, rejects
private/loopback/link-local/multicast/reserved IPs, caps redirects,
re-validates the resolved IP on every hop, and enforces a response size cap.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings


class SSRFBlockedError(Exception):
    """Raised when a URL (or a redirect target) is disallowed - unresolvable
    host, private/internal IP, disallowed scheme, too many redirects, or a
    response over the size cap."""


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


async def _resolve_and_validate(hostname: str) -> None:
    """Resolves every A/AAAA record for hostname and rejects the whole host if
    ANY resolved address is private/internal - a hostname that resolves to
    both a public and an internal address (DNS rebinding / split-horizon
    attack surface) must not be trusted just because one answer looked safe.
    """
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Could not resolve host: {hostname}") from exc

    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise SSRFBlockedError(f"No addresses resolved for host: {hostname}")
    for ip in addresses:
        if _is_blocked_ip(ip):
            raise SSRFBlockedError(f"Host {hostname} resolves to a disallowed address: {ip}")


async def safe_fetch(url: str, *, max_bytes: int | None = None, headers: dict[str, str] | None = None) -> str:
    """Fetches `url` and returns its response body as text, following
    redirects manually (not httpx's built-in follow_redirects) so every hop's
    target gets the same hostname-resolution + private-IP check as the
    original URL, not just the first one.

    headers: passed through as-is (e.g. an identifying User-Agent - see
    discovery/startupmap.py, which sends one rather than an anonymous/spoofed
    default, since the sites this hits have explicitly said crawlers are
    welcome and a real identity is what lets them selectively rate-limit or
    block us later if they ever need to, unlike an anonymous default would).

    Raises SSRFBlockedError if the URL or any redirect target is disallowed,
    or if the response exceeds the configured size cap.
    """
    max_bytes = max_bytes or settings.startup_hunt_ssrf_max_response_bytes
    current_url = url

    async with httpx.AsyncClient(
        timeout=settings.startup_hunt_ssrf_timeout_seconds, follow_redirects=False, headers=headers
    ) as client:
        for _ in range(settings.startup_hunt_ssrf_max_redirects + 1):
            parsed = urlparse(current_url)
            if parsed.scheme not in ("http", "https"):
                raise SSRFBlockedError(f"Disallowed URL scheme: {parsed.scheme}")
            if not parsed.hostname:
                raise SSRFBlockedError("URL has no hostname")

            await _resolve_and_validate(parsed.hostname)

            async with client.stream("GET", current_url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise SSRFBlockedError("Redirect with no Location header")
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise SSRFBlockedError(f"Response exceeded {max_bytes} byte cap")
                    chunks.append(chunk)
                return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    raise SSRFBlockedError("Too many redirects")
