# Resume Tailor: Low-Level Design (LLD)

**Document Version:** 1.0.0
**Status:** Approved for Production
**Target Audience:** Software Engineers, Module Owners

---

## 1. Code Architecture & Component Directory

```
apps/api/app/modules/resume_tailor/
├── __init__.py
├── routes.py              # FastAPI endpoints, session lifecycle, resume ingestion orchestration
├── saved_resumes_routes.py # "My Resumes" CRUD (up to 3 slots/user), included into routes.py's router
├── sessions_routes.py     # GET /tailor/sessions — "My Docs" list
├── generation.py          # Every LLM call: JD/resume chunking, base CV structuring, tailoring prose
├── prompts.py             # Prompt text + version constants (cache-busting keys)
├── chunker.py             # Pure regex/heuristic chunking — the LLM-primary paths' fallback
├── matcher.py             # Deterministic matching: keywords, cosine similarity, scoring, gaps — zero AI
├── validation.py          # Anti-hallucination checks on LLM output (prose fields + chunking repair)
├── schemas.py             # Pydantic request/response models + CvDataSchema
├── models.py              # SQLAlchemy ORM: ResumeVersion, TailoringSession, SavedResume
├── repository.py          # Postgres access via UserScopedRepository
├── cache.py                # Redis layer: resume blob, JD chunk (cross-user), prose, locks
├── rendering.py            # Jinja template fill + WeasyPrint PDF export, no AI
├── extraction.py           # Deterministic resume parsing (PyMuPDF text extraction, fallback CV structuring)
└── service.py              # Misc: saved-resume file fetch, ownership verification, "My Docs" listing
```

---

## 2. Core Service Workflows

### 2.1 Resume Ingestion (`routes.py::_resolve_resume_version`)

```python
async def _resolve_resume_version(
    db: AsyncSession, user_id: str, pdf_bytes: bytes, resume_hash: str,
) -> tuple[ResumeVersion, list[Chunk], np.ndarray]:
```

1. **Redis hit** (`resume_cache.get_resume_cache`): return cached `(text, chunks, embeddings)` directly — no staleness check on this path (same pre-existing limitation as the Postgres path's `embeddings_model` check had before `chunks_version` was added; self-heals on TTL expiry).
2. **Postgres hit, Redis miss**: load the row, then two staleness checks in order:
   - `chunks_version != RESUME_CHUNK_PROMPT_VERSION` → re-chunk via `generation.chunk_resume_with_llm_repair`, which **forces** `resume_embeddings` to empty (new chunk boundaries invalidate old embeddings — they're stored position-aligned to `chunks`).
   - `embeddings_model != current model_label OR embeddings empty` → re-embed.
   - Persist whatever changed in one `repo.update(**update_fields)` call, warm Redis.
3. **Absent from both**: extract text (PyMuPDF, off the event loop via `asyncio.to_thread`), chunk via `chunk_resume_with_llm_repair` (LLM-primary, `chunk_resume` as fallback), embed, `INSERT` with `chunks_version=RESUME_CHUNK_PROMPT_VERSION`, warm Redis.

This only runs the LLM chunking call once per (user, PDF hash) — every subsequent `/tailor` request with the same resume hits step 1 or 2's no-op path.

### 2.2 Main Orchestration (`routes.py::tailor_resume`)

```python
@router.post("/tailor", response_model=TailorResponse)
async def tailor_resume(..., job_description: str, force_refresh: bool, ...):
```

1. Rate limit + resume ingestion (§2.1).
2. **Session dedup**: `TailoringSessionRepository.get_or_create_session(user_id, resume_version_id, job_hash, matcher_version, prompt_version)` — a hit on the exact same (resume, JD, matcher/prompt version) tuple returns the durable result with zero new AI calls.
3. **Single-flight lock** (`resume_cache.acquire_tailor_lock`) around everything from JD-onward, so two concurrent identical submissions don't both pay for a JD embeddings call.
4. **JD ingestion**: `translate_jd_if_needed` → `clean_jd_text` → check the **JD chunk cache** (`resume_cache.get_jd_chunk_cache`, keyed on `compute_jd_hash(cleaned_text)` + `JD_CHUNK_PROMPT_VERSION`, NOT user-scoped) → on miss, `chunk_jd_with_llm_repair` (LLM-primary, `chunk_jd` fallback) + embed, then write the cache entry (chunks + embeddings bundled together, so a hit skips both the LLM call and the embeddings API call).
5. **Deterministic match**: `matcher.match_resume_to_jd(resume_chunks, resume_embeddings, jd_chunks, jd_embeddings, ...)` → `MatchResult`.
6. **Prose**: `generation.generate_tailor_prose(...)` — one LLM call, validated, cached separately (resume_hash + job_hash + prompt_version + model).
7. **Persist**: `TailoringSessionRepository.create_session(...)` with `matcher_version`/`prompt_version` baked in.

---

## 3. Algorithmic Specifications

### 3.1 LLM-Primary Chunking Repair Pattern (`generation.py`)

Both `chunk_jd_with_llm_repair` and `chunk_resume_with_llm_repair` share one contract:

```python
async def chunk_jd_with_llm_repair(jd_text_clean: str, regex_chunks: list[Chunk]) -> tuple[list[Chunk], bool]:
    try:
        raw = await ai_provider.generate_text(..., response_format={"type": "json_object"}, reasoning_effort=...)
    except ai_provider.AIGenerationError:
        return regex_chunks, jd_chunking_is_pathological(regex_chunks, jd_text_clean)
    # parse JSON; on failure -> same fallback
    chunked = validate_llm_jd_chunks(parsed.get("chunks") or [], jd_text_clean)
    if chunked is None:  # failed verbatim/coverage validation
        return regex_chunks, jd_chunking_is_pathological(regex_chunks, jd_text_clean)
    return chunked, False
```

`degraded=True` only when **both** the LLM path failed **and** the regex fallback's own output looks structurally broken (`*_chunking_is_pathological`) — a merely-imperfect fallback is not flagged, since there's no reliable statistical way to detect "slightly wrong" at this layer.

### 3.2 Verbatim/Coverage Validation (`validation.py`)

`validate_llm_jd_chunks` / `validate_llm_resume_chunks` never trust the LLM's chunk text outright:

```python
def validate_llm_jd_chunks(raw_chunks: list[dict], source_text: str) -> list[Chunk] | None:
    # every candidate chunk's kind must be in the fixed vocabulary
    # every candidate chunk's text must be a whitespace-normalized VERBATIM
    # substring of source_text — paraphrased/invented chunks are silently dropped
    # if total kept coverage / total source length < 0.5 -> reject the WHOLE attempt
    # survivors are re-sorted into source-document order before returning
```

The resume-chunk variant adds one more check the JD variant doesn't need: `section` must be one of the fixed vocabulary (`experience`, `projects`, `education`, `skills`, `summary`, `publications`, `certifications`, `languages`, `header`) — JD chunk sections are fully determined by `kind`, resume sections are not.

### 3.3 Deterministic Matching (`matcher.py::match_resume_to_jd`)

```python
S = similarity_matrix(resume_embeddings, jd_embeddings)  # (n_resume, n_jd), cosine via normalized dot product
for j_idx, jd_chunk in enumerate(jd_chunks):
    col = S[:, j_idx]
    best_score = col.max()
    match_type = "strong" if best_score >= 0.72 else "partial" if best_score >= 0.55 else "missing"
```

- **Keyword layer**: `extract_keywords` (structural shapes — acronyms/CamelCase/dotted — plus a bounded allowlist of ~300 tech terms) runs independently of embeddings, with a product→category inference step (e.g. `ChromaDB` → also adds `"vector database"`) so a specific implementation grounds a generic category ask.
- **Critical gaps**: a `requirement`-kind JD chunk with `match_type == "missing"` AND no keyword overlap (two-pass: extracted tokens, then substring fallback).
- **Rewrite candidates**: per JD `requirement` chunk, the top-3 resume bullets by similarity that land in `REWRITE_BAND` (0.45–0.82) — meaningful overlap, but framing could be sharpened — capped at `MAX_REWRITE_BULLETS` (7) overall.
- **Score breakdown**: category-weighted average of per-kind match scores; when a JD has no `domain`-kind chunks at all (common — many postings skip "About Us"), that category's weight is redistributed proportionally rather than scored 0, so a well-matched JD with no company blurb isn't penalized for an absence of signal.

---

## 4. Resilience & Fallback Contracts

| Failure | Behavior |
| :--- | :--- |
| AI provider chain exhausted (chunking) | Falls back to regex chunker; `degraded=True` only if that fallback also looks pathological. |
| AI provider chain exhausted (prose) | `TailorProseResult.ai_status = "degraded"`; a deterministic fit summary (`_deterministic_fit_summary`) fills the panel instead of an empty box; `tailored_summary`/`bullet_rewrites` stay empty (never partially-AI content on the exported resume). |
| AI provider chain exhausted (base CV structuring) | Deterministic PyMuPDF/regex extraction (`extraction.py::build_base_cv_data_deterministic`) — lower fidelity, but the editor stays usable. |
| Embeddings provider (Jina/Cohere) down | Keyword-only matching, `degraded: true` on the analysis. |
| Redis down | Rate limits and locks fail open; cache misses are non-fatal (fall through to Postgres/a real AI call). |
| LLM chunking/prose output fails validation | Rejected wholesale (chunking) or sentence-level salvage (`repair_summary` for the tailored summary) rather than discarding valid content for one bad clause. |
