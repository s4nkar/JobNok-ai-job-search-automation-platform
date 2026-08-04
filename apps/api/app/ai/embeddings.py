"""External embedding provider abstraction — Jina primary, Cohere fallback.

Both APIs return L2-normalized float32 vectors. Output shape: (n, dim).
We treat the dimension as opaque — comparisons happen between vectors produced
by the same provider in a single call, so dim consistency is guaranteed.

Public surface:
    embed(texts: list[str], purpose: str = "matching") -> np.ndarray
        Encodes a batch. Empty input returns shape (0, 0).
        `purpose` is provider-specific (e.g. Jina v3 supports task hints).
    similarity_matrix(A, B) -> np.ndarray
        Pairwise cosine similarity. Assumes both A and B are L2-normalized
        (which embed() guarantees).
    EmbeddingError
        Raised when all providers fail. Callers should fall back to
        keyword-only matching rather than failing the request entirely.

No vector DB. No local model. No torch. Just HTTP + numpy.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from app.core.config import settings

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """All embedding providers exhausted. Caller should degrade gracefully."""


class _ProviderError(Exception):
    """Transient provider failure — try next in chain."""


class _ProviderUnavailable(_ProviderError):
    """Provider not configured (missing key) — skip silently."""


# ── Jina ──────────────────────────────────────────────────────────

async def _jina_embed(texts: list[str], purpose: str) -> "np.ndarray":
    import numpy as np
    if not settings.jina_api_key:
        raise _ProviderUnavailable("jina: API key not configured")

    # Jina v3 task hints: retrieval.query | retrieval.passage | text-matching |
    # classification | separation. For symmetric resume↔JD comparison we use
    # text-matching.
    task = "text-matching" if purpose == "matching" else "retrieval.passage"

    try:
        async with httpx.AsyncClient(timeout=settings.embedding_request_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.jina_base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.jina_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.jina_model,
                    "task": task,
                    "input": texts,
                    "embedding_type": "float",
                    "normalized": True,
                },
            )
    except httpx.HTTPError as exc:
        raise _ProviderError(f"jina network error: {exc!r}") from exc

    if resp.status_code == 429 or resp.status_code >= 500:
        raise _ProviderError(f"jina HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        # 4xx (other than 429) = request shape problem. Don't retry on another
        # provider — re-raise so the bug surfaces.
        raise RuntimeError(f"jina HTTP {resp.status_code}: {resp.text[:200]}")

    payload = resp.json()
    try:
        # Jina returns sorted by index; we still sort defensively.
        items = sorted(payload["data"], key=lambda d: d["index"])
        vectors = np.asarray([item["embedding"] for item in items], dtype="float32")
    except (KeyError, TypeError, ValueError) as exc:
        raise _ProviderError(f"jina malformed response: {exc!r}") from exc

    return _ensure_normalized(vectors)


# ── Cohere ────────────────────────────────────────────────────────

async def _cohere_embed(texts: list[str], purpose: str) -> "np.ndarray":
    import numpy as np
    if not settings.cohere_api_key:
        raise _ProviderUnavailable("cohere: API key not configured")

    # Cohere requires an input_type. search_document is symmetric-friendly;
    # for query-side use search_query. We use search_document for both sides
    # (symmetric matching, not asymmetric retrieval).
    input_type = "search_document"

    try:
        async with httpx.AsyncClient(timeout=settings.embedding_request_timeout_seconds) as client:
            resp = await client.post(
                f"{settings.cohere_base_url}/embed",
                headers={
                    "Authorization": f"Bearer {settings.cohere_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.cohere_embedding_model,
                    "input_type": input_type,
                    "texts": texts,
                    "embedding_types": ["float"],
                },
            )
    except httpx.HTTPError as exc:
        raise _ProviderError(f"cohere network error: {exc!r}") from exc

    if resp.status_code == 429 or resp.status_code >= 500:
        raise _ProviderError(f"cohere HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        raise RuntimeError(f"cohere HTTP {resp.status_code}: {resp.text[:200]}")

    payload = resp.json()
    try:
        floats = payload["embeddings"]["float"]
        vectors = np.asarray(floats, dtype="float32")
    except (KeyError, TypeError, ValueError) as exc:
        raise _ProviderError(f"cohere malformed response: {exc!r}") from exc

    return _ensure_normalized(vectors)


# ── Dispatch ──────────────────────────────────────────────────────

def _ensure_normalized(vectors: "np.ndarray") -> "np.ndarray":
    """Defence-in-depth L2 normalize — providers may return non-normalized vectors
    on edge cases (zero-length input strings, etc.)."""
    import numpy as np
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    # Avoid divide-by-zero for any all-zero rows.
    norms[norms == 0] = 1.0
    return vectors / norms


def _provider_chain() -> list[str]:
    primary = settings.embedding_provider.lower().strip()
    fallbacks = [p.strip().lower() for p in settings.embedding_fallback_chain.split(",") if p.strip()]
    return [primary] + [p for p in fallbacks if p != primary]


async def _dispatch(provider: str, texts: list[str], purpose: str) -> "np.ndarray":
    if provider == "jina":
        return await _jina_embed(texts, purpose)
    if provider == "cohere":
        return await _cohere_embed(texts, purpose)
    raise ValueError(f"Unknown embedding provider: {provider!r}")


# ── Public Interface ──────────────────────────────────────────────

async def embed(texts: list[str], purpose: str = "matching") -> "np.ndarray":
    """Embed a batch of texts. Returns L2-normalized float32 vectors (n, dim).

    Raises EmbeddingError if every configured provider fails. Callers that want
    to degrade gracefully (keyword-only matching) should catch this.
    """
    import numpy as np
    if not texts:
        return np.zeros((0, 0), dtype="float32")

    chain = _provider_chain()
    last_error: Exception | None = None
    for provider in chain:
        try:
            return await _dispatch(provider, texts, purpose)
        except _ProviderUnavailable as exc:
            logger.info("embeddings skip %s: %s", provider, exc)
            last_error = exc
            continue
        except _ProviderError as exc:
            logger.warning("embeddings transient failure on %s: %s", provider, exc)
            last_error = exc
            continue
    raise EmbeddingError(f"All embedding providers exhausted ({chain}). Last error: {last_error!r}")


def similarity_matrix(A: "np.ndarray", B: "np.ndarray") -> "np.ndarray":
    """Pairwise cosine similarity between row-vectors of A (m, d) and B (n, d).

    Both inputs must be L2-normalized (embed() guarantees this). Returns (m, n).
    If either side is empty, returns an empty matrix with the correct shape.
    """
    import numpy as np
    if A.size == 0 or B.size == 0:
        return np.zeros((A.shape[0], B.shape[0]), dtype="float32")
    return A @ B.T
