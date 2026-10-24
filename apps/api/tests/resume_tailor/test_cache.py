"""Unit tests for resume_tailor.cache — hash determinism and the jdchunk
cache wrappers, with the Redis layer (get_cached/set_cached) faked via an
in-memory dict so no live Redis connection is needed."""

from app.modules.resume_tailor import cache as resume_cache


class _FakeRedis:
    """Minimal in-memory stand-in for app.services.cache.get_cached/set_cached,
    enough to exercise key construction, (de)serialization, and TTL plumbing
    without a real connection."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self.store[key] = value
        self.set_calls.append((key, value, ttl_seconds))


def _patch_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(resume_cache, "get_cached", fake.get)
    monkeypatch.setattr(resume_cache, "set_cached", fake.set)
    return fake


# ── Hash determinism ──────────────────────────────────────────────────

def test_compute_jd_hash_deterministic_for_same_text():
    a = resume_cache.compute_jd_hash("Same posting, cleaned text.")
    b = resume_cache.compute_jd_hash("Same posting, cleaned text.")
    assert a == b


def test_compute_jd_hash_differs_for_different_text():
    a = resume_cache.compute_jd_hash("Posting A.")
    b = resume_cache.compute_jd_hash("Posting B.")
    assert a != b


def test_compute_jd_hash_strips_surrounding_whitespace():
    # Two callers passing the "same" cleaned text with incidental leading/
    # trailing whitespace differences must still hit the same cache key.
    a = resume_cache.compute_jd_hash("Same posting, cleaned text.")
    b = resume_cache.compute_jd_hash("  Same posting, cleaned text.\n")
    assert a == b


def test_compute_resume_hash_deterministic_for_same_bytes():
    pdf_bytes = b"%PDF-1.4 fake pdf content"
    assert resume_cache.compute_resume_hash(pdf_bytes) == resume_cache.compute_resume_hash(pdf_bytes)


def test_compute_resume_hash_differs_for_different_bytes():
    assert resume_cache.compute_resume_hash(b"one") != resume_cache.compute_resume_hash(b"two")


# ── JD chunk cache ─────────────────────────────────────────────────────

async def test_jd_chunk_cache_round_trips(monkeypatch):
    _patch_redis(monkeypatch)
    jd_hash = resume_cache.compute_jd_hash("Some cleaned JD text.")
    entry = {
        "chunks": [{"kind": "requirement", "section": "requirements", "text": "Needs Python."}],
        "degraded": False,
        "embeddings": [[0.1, 0.2]],
        "embeddings_model": "jina-embeddings-v3",
    }

    assert await resume_cache.get_jd_chunk_cache(jd_hash, "jdchunk-v2") is None  # miss before write

    await resume_cache.set_jd_chunk_cache(jd_hash, "jdchunk-v2", entry)
    got = await resume_cache.get_jd_chunk_cache(jd_hash, "jdchunk-v2")

    assert got == entry


async def test_jd_chunk_cache_not_shared_across_prompt_versions(monkeypatch):
    # A JD_CHUNK_PROMPT_VERSION bump must bust this cache — same jd_hash,
    # different version, should miss.
    _patch_redis(monkeypatch)
    jd_hash = resume_cache.compute_jd_hash("Some cleaned JD text.")
    await resume_cache.set_jd_chunk_cache(jd_hash, "jdchunk-v1", {"chunks": [], "degraded": False})

    assert await resume_cache.get_jd_chunk_cache(jd_hash, "jdchunk-v2") is None


async def test_jd_chunk_cache_not_shared_across_different_jd_text(monkeypatch):
    _patch_redis(monkeypatch)
    hash_a = resume_cache.compute_jd_hash("Posting A.")
    hash_b = resume_cache.compute_jd_hash("Posting B.")
    await resume_cache.set_jd_chunk_cache(hash_a, "jdchunk-v2", {"chunks": ["a"], "degraded": False})

    assert await resume_cache.get_jd_chunk_cache(hash_b, "jdchunk-v2") is None


async def test_jd_chunk_cache_key_is_not_scoped_by_user():
    # Unlike the resume/prose caches, jdchunk is deliberately global — two
    # different users with the same cleaned JD text must produce the exact
    # same cache key so they share one cached chunking result.
    jd_hash = resume_cache.compute_jd_hash("Same posting.")
    key_fn = resume_cache._jd_chunk_cache_key  # internal, but this IS the behavior under test
    assert key_fn(jd_hash, "jdchunk-v2") == key_fn(jd_hash, "jdchunk-v2")
    assert "user" not in key_fn(jd_hash, "jdchunk-v2").lower()


async def test_jd_chunk_cache_get_returns_none_on_malformed_json(monkeypatch):
    fake = _patch_redis(monkeypatch)
    jd_hash = resume_cache.compute_jd_hash("Some cleaned JD text.")
    fake.store[resume_cache._jd_chunk_cache_key(jd_hash, "jdchunk-v2")] = "not valid json"

    assert await resume_cache.get_jd_chunk_cache(jd_hash, "jdchunk-v2") is None


async def test_jd_chunk_cache_set_uses_jd_ttl_not_resume_ttl(monkeypatch):
    # jdchunk uses a 7-day TTL (postings get edited/pulled), distinct from
    # the resume blob's 30-day TTL — a regression here would silently make
    # stale JD chunking linger as long as a resume does.
    fake = _patch_redis(monkeypatch)
    jd_hash = resume_cache.compute_jd_hash("Some cleaned JD text.")
    await resume_cache.set_jd_chunk_cache(jd_hash, "jdchunk-v2", {"chunks": [], "degraded": False})

    assert fake.set_calls[-1][2] == resume_cache._JD_CHUNK_CACHE_TTL_SECONDS
    assert resume_cache._JD_CHUNK_CACHE_TTL_SECONDS == 60 * 60 * 24 * 7


# ── Resume blob cache (compute_resume_hash's sibling get/set — no prior
# coverage existed for these either) ────────────────────────────────────

async def test_resume_cache_round_trips(monkeypatch):
    _patch_redis(monkeypatch)
    entry = {"text": "resume text", "chunks": [{"kind": "bullet", "section": "experience", "text": "Did a thing."}]}

    assert await resume_cache.get_resume_cache("user-1", "hash-1") is None

    await resume_cache.set_resume_cache("user-1", "hash-1", entry)
    assert await resume_cache.get_resume_cache("user-1", "hash-1") == entry


async def test_update_resume_cache_merges_into_existing_entry(monkeypatch):
    _patch_redis(monkeypatch)
    await resume_cache.set_resume_cache("user-1", "hash-1", {"text": "resume text"})

    merged = await resume_cache.update_resume_cache("user-1", "hash-1", chunks_version="resumechunk-v1")

    assert merged == {"text": "resume text", "chunks_version": "resumechunk-v1"}
    assert await resume_cache.get_resume_cache("user-1", "hash-1") == merged


async def test_resume_cache_key_is_scoped_by_user():
    assert resume_cache._cache_key("user-1", "hash-1") != resume_cache._cache_key("user-2", "hash-1")


# ── Embeddings (de)serialization ─────────────────────────────────────

def test_serialize_deserialize_embeddings_round_trip():
    import numpy as np

    arr = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype="float32")
    restored = resume_cache.deserialize_embeddings(resume_cache.serialize_embeddings(arr))
    assert np.allclose(restored, arr)


def test_deserialize_embeddings_handles_none_and_empty():
    import numpy as np

    assert resume_cache.deserialize_embeddings(None).shape == (0, 0)
    assert resume_cache.deserialize_embeddings([]).shape == (0, 0)
    assert isinstance(resume_cache.deserialize_embeddings(None), np.ndarray)
