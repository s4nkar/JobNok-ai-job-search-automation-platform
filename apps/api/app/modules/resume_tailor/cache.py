"""Resume content + tailoring prose cache.

Redis is a read-through accelerator in front of the resume_tailor Postgres
tables (resume_versions/tailoring_sessions, see models.py) — Postgres is the
source of truth; a cache miss/failure here just costs a Postgres read or an
LLM call, never data loss.

Key layout:
    resume:{user_id}:{sha256}  →  JSON {
        "text":       str,
        "chunks":     [{"kind", "section", "text"}, ...],
        "embeddings": [[float, ...], ...],   # same order as chunks
        "base_cv_data": {...} | absent,
        "base_cv_data_prompt_version": str | absent,
    }
    prose:{user_id}:{resume_hash}:{job_hash}:{prompt_version}:{model} → JSON tailoring prose

The hash is scoped per user_id to prevent cross-user content inference via cache
timing (knowing whether another user uploaded the same resume).
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.services.cache import acquire_lock, get_cached, set_cached

if TYPE_CHECKING:
    import numpy as np

# 30 days — resumes change rarely; users who re-tailor against new JDs benefit
# from the cached parse on every subsequent request.
_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30


def compute_resume_hash(pdf_bytes: bytes) -> str:
    """SHA256 of the raw PDF bytes. Deterministic per file content."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def _cache_key(user_id: str, resume_hash: str) -> str:
    return f"resume:{user_id}:{resume_hash}"


async def get_resume_cache(user_id: str, resume_hash: str) -> dict[str, Any] | None:
    raw = await get_cached(_cache_key(user_id, resume_hash))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def set_resume_cache(user_id: str, resume_hash: str, entry: dict[str, Any]) -> None:
    await set_cached(
        _cache_key(user_id, resume_hash),
        json.dumps(entry),
        ttl_seconds=_CACHE_TTL_SECONDS,
    )


async def update_resume_cache(user_id: str, resume_hash: str, **fields: Any) -> dict[str, Any]:
    """Merge new fields into an existing cache entry (or create one). Returns the merged entry.

    Used by later phases to attach structured JSON and embeddings to the same
    cache entry without re-extracting the resume text.
    """
    existing = await get_resume_cache(user_id, resume_hash) or {}
    existing.update(fields)
    await set_resume_cache(user_id, resume_hash, existing)
    return existing


def serialize_embeddings(vectors: "np.ndarray") -> list[list[float]]:
    """Convert a (n, dim) numpy array to a JSON-serializable nested list.

    Float32 stays as Python float — JSON has no float32 distinction, and we
    re-normalize on load anyway.
    """
    return vectors.tolist()


def deserialize_embeddings(raw: list[list[float]] | None) -> "np.ndarray":
    """Restore embeddings stored as nested lists back to a (n, dim) float32 array.

    Returns shape (0, 0) for None / empty input so callers can treat absence
    and zero-length uniformly.
    """
    import numpy as np
    if not raw:
        return np.zeros((0, 0), dtype="float32")
    return np.asarray(raw, dtype="float32")


# ── Tailoring prose cache ────────────────────────────────────────────
# Distinct from the resume blob above: keyed by (resume_hash, job_hash,
# prompt_version, model) since the same resume tailored against the same JD
# should reuse the same AI prose until the prompt or model changes — there is
# no existing analog for this (cached_prompt_parse in app/services/cache.py
# hashes prompt text only, with no version/model axis).

_PROSE_CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
_PROSE_LOCK_TTL_SECONDS = settings.ai_request_timeout_seconds + 5  # covers one LLM call
PROSE_SINGLE_FLIGHT_POLL_INTERVAL_SECONDS = 0.5
PROSE_SINGLE_FLIGHT_MAX_WAIT_SECONDS = 10


def _prose_cache_key(user_id: str, resume_hash: str, job_hash: str, prompt_version: str, model: str) -> str:
    # user_id stays in the key for the same cross-user cache-timing-inference
    # reason documented on the resume blob's key above.
    return f"prose:{user_id}:{resume_hash}:{job_hash}:{prompt_version}:{model}"


async def get_prose_cache(
    user_id: str, resume_hash: str, job_hash: str, prompt_version: str, model: str,
) -> dict[str, Any] | None:
    raw = await get_cached(_prose_cache_key(user_id, resume_hash, job_hash, prompt_version, model))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def set_prose_cache(
    user_id: str, resume_hash: str, job_hash: str, prompt_version: str, model: str, entry: dict[str, Any],
) -> None:
    await set_cached(
        _prose_cache_key(user_id, resume_hash, job_hash, prompt_version, model),
        json.dumps(entry),
        ttl_seconds=_PROSE_CACHE_TTL_SECONDS,
    )


async def acquire_prose_lock(user_id: str, resume_hash: str, job_hash: str, prompt_version: str) -> bool:
    """Single-flight lock so two concurrent identical tailoring requests don't
    both fire the same LLM call. Mirrors the existing acquire_lock usage in
    job_search/startup_hunt/startup_scout service.py — fail-open (treat as
    leader) is the caller's responsibility on a Redis error, same as those."""
    key = f"prose:{user_id}:{resume_hash}:{job_hash}:{prompt_version}:lock"
    return await acquire_lock(key, _PROSE_LOCK_TTL_SECONDS)
