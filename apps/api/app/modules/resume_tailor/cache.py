"""Resume content cache.

Hashes uploaded PDF bytes and caches the extracted text + chunked structure +
embedding vectors so repeat uploads skip every expensive step.

Key layout:
    resume:{user_id}:{sha256}  →  JSON {
        "text":       str,
        "chunks":     [{"kind", "section", "text"}, ...],
        "embeddings": [[float, ...], ...]   # same order as chunks
    }

The hash is scoped per user_id to prevent cross-user content inference via cache
timing (knowing whether another user uploaded the same resume).
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from app.services.cache import get_cached, set_cached

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
