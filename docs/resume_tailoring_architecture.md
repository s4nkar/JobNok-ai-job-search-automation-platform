# Resume Tailoring Tool — Architecture (Implemented)

## Goal

Build a production-quality AI-powered resume tailoring system that:

- Understands resumes and job descriptions structurally
- Produces explainable ATS-style scoring (per-category breakdown)
- Detects transferable skills intelligently (embedding-based)
- Avoids generic AI fluff (deterministic matcher, no AI in analysis layer)
- Preserves strong technical experience (only rewrite weak/transferable bullets)
- Generates truthful rewrite suggestions (LLM only for prose, grounded in deterministic analysis)
- Mimics how strong recruiters actually evaluate candidates

## Implementation Status

✅ **IMPLEMENTED** — Phases 1–6 complete (2026-05-13)

This architecture intentionally separates:
- **Deterministic processing** (chunking, keyword extraction, embedding lookup, scoring)
- **Semantic understanding** (external Jina/Cohere embeddings, no local model)
- **LLM reasoning** (small targeted call for prose only, grounded in deterministic results)

---

# High-Level System Flow (Actual)

```text
User Uploads Resume + Pastes JD
                ↓
    ┌──────────────────────────┐
    │  Resume (Cached Path)    │
    ├──────────────────────────┤
    │ 1. Hash bytes (SHA256)   │
    │ 2. Check Redis cache     │
    │ 3. If miss: PyMuPDF      │
    │ 4. Store {text, chunks,  │
    │    embeddings} in Redis  │
    │ (30-day TTL per hash)    │
    └──────────────────────────┘
                ↓
    ┌──────────────────────────┐
    │  JD (Always Fresh)       │
    ├──────────────────────────┤
    │ 1. Regex chunking        │
    │ 2. Jina/Cohere embed     │
    │ (no cache)               │
    └──────────────────────────┘
                ↓
    ┌──────────────────────────┐
    │  Deterministic Matching  │
    ├──────────────────────────┤
    │ • Similarity matrix      │
    │ • Per-requirement evidence
    │ • Keyword overlap        │
    │ • Score breakdown        │
    │ • Gap classification     │
    │ (no LLM, ~10ms, numpy)   │
    └──────────────────────────┘
                ↓
    ┌──────────────────────────┐
    │  LLM Prose Generation    │
    ├──────────────────────────┤
    │ Prompt includes:         │
    │ • Deterministic scores   │
    │ • Matched keywords       │
    │ • Critical gaps          │
    │ • Transferable bullets   │
    │                          │
    │ Returns:                 │
    │ • Headline, summary      │
    │ • Bullet rewrites        │
    │ • Fit assessment         │
    │ (~1.2k tokens, Groq)     │
    └──────────────────────────┘
                ↓
          Merge & Return
                ↓
    ┌──────────────────────────┐
    │  Final Report (JSON)     │
    ├──────────────────────────┤
    │ Deterministic:           │
    │ • match_score (0-100)    │
    │ • score_breakdown {}     │
    │ • matched_keywords []    │
    │ • transferable_strengths │
    │ • critical_missing []    │
    │                          │
    │ AI-Generated:            │
    │ • profile_headline       │
    │ • tailored_summary       │
    │ • bullet_rewrites []     │
    │ • summary (recruiter fit)│
    └──────────────────────────┘
                ↓
          Frontend UI
          (React + Charts)
```

---

# 1. Input Guardrail Layer

## Purpose

Clean, validate, normalize, and structure incoming job descriptions before any downstream processing.

This layer is critical because:
- many JDs are noisy
- ATS exports are duplicated
- scraped jobs contain metadata junk
- poor input reduces model quality dramatically

---

## Responsibilities

### 1.1 Remove Noise

Remove:
- duplicate paragraphs
- repeated sections
- ATS export metadata
- role signals
- apply links
- recruiter notes
- UI helper text
- tracking text
- irrelevant footer content

Example removals:

```text
Matched role keywords
Apply now
Paste full JD below
Role signals
English-friendly company
```

---

### 1.2 Normalize Formatting

Convert:
- bullets
- spacing
- unicode symbols
- inconsistent line breaks

into standardized clean text.

---

### 1.3 Section Detection

Detect and separate:
- title
- company
- location
- responsibilities
- requirements
- preferred skills
- benefits
- about company

---

### 1.4 Input Quality Validation

Detect:
- empty JDs
- partial JDs
- multiple jobs pasted together
- spam content
- recruiter outreach emails
- non-job text

---

## Output Schema

```json
{
  "clean_jd_text": "",
  "job_title": "",
  "company": "",
  "location": "",
  "sections": {},
  "input_quality": "good | partial | poor",
  "warnings": []
}
```

---

# 2. Resume Parser Layer

## Purpose

Convert uploaded resumes into structured machine-readable data.

This layer should:
- extract only
- not rewrite
- preserve evidence exactly

---

## Responsibilities

Extract:

- summary
- experience
- projects
- education
- skills
- tools
- metrics
- publications
- certifications
- languages

---

## Important Rules

### Preserve Original Bullets

Do NOT:
- simplify
- rewrite
- paraphrase

Strong technical bullets must remain untouched until rewrite analysis later.

---

## Output Schema

```json
{
  "headline": "",
  "summary": "",
  "experience": [],
  "projects": [],
  "education": [],
  "skills": [],
  "tools": [],
  "metrics": [],
  "publications": [],
  "languages": []
}
```

---

# 3. JD Parser Layer

## Purpose

Convert cleaned JD text into structured hiring requirements.

This layer transforms unstructured recruiter language into machine-readable requirements.

---

## Responsibilities

Extract:

- required skills
- preferred skills
- responsibilities
- technologies
- domain requirements
- seniority
- education requirements
- language requirements
- soft skills
- hidden recruiter signals

---

## Hidden Signal Detection

Example:

JD says:

```text
Collaborate cross-functionally
```

Hidden signal:

```json
{
  "teamwork": true,
  "stakeholder_communication": true
}
```

---

## Output Schema

```json
{
  "required_skills": [],
  "preferred_skills": [],
  "responsibilities": [],
  "domain_keywords": [],
  "tools": [],
  "seniority": "",
  "education_requirements": [],
  "language_requirements": [],
  "hidden_signals": []
}
```

---

# 4. Embedding Generation Layer

## Purpose

Convert resume and JD components into vector embeddings for semantic comparison.

This layer enables:
- semantic similarity
- transferable skill detection
- adjacent domain matching
- non-keyword understanding

Without embeddings:
- the system becomes keyword-based
- semantic reasoning becomes weak
- transferable experience gets missed

---

## Why Embeddings Matter

Keyword matching alone fails for cases like:

```text
Resume:
Built scalable NLP pipelines

JD:
Experience with large-scale ML data pipelines
```

Keywords differ.

Meaning overlaps.

Embeddings allow the system to understand this relationship.

---

## Recommended Embedding Targets

Generate embeddings for:

### Resume
- bullets
- projects
- skills
- summaries
- publications

### JD
- requirements
- responsibilities
- preferred skills
- domain statements

---

## Recommended Models

### OpenAI
- text-embedding-3-large
- text-embedding-3-small

### Open Source
- BGE Large
- Jina Embeddings
- E5 Large

---

## Storage Recommendation

Store embeddings in:
- pgvector
- Pinecone
- Weaviate
- Qdrant
- ChromaDB

---

## Output Schema

```json
{
  "embedding_id": "",
  "source": "resume | jd",
  "section_type": "",
  "text": "",
  "vector": []
}
```

---

# 5. Semantic Matching Engine

## Purpose

Map resume evidence against JD requirements.

This is the intelligence layer of the system.

---

## Responsibilities

For each JD requirement:
- identify supporting evidence
- classify match strength
- calculate confidence score
- detect transferable alignment

---

## Matching Types

### Exact Match

Example:

```text
PyTorch ↔ PyTorch
```

---

### Semantic Match

Example:

```text
Distributed NLP pipelines
↔
Large-scale ML pipelines
```

---

### Transferable Match

Example:

```text
Multimodal AI
↔
Computer Vision Adjacent Experience
```

---

## Output Schema

```json
{
  "requirement": "",
  "match_status": "strong | partial | missing",
  "resume_evidence": [],
  "confidence": 0.0,
  "match_type": "exact | semantic | transferable"
}
```

---

# 6. Scoring Engine

## Purpose

Generate explainable ATS-style scoring.

Avoid vague single-number scoring.

---

## Responsibilities

Generate:
- overall match
- skill match
- domain alignment
- production experience
- MLOps alignment
- seniority fit
- ATS keyword coverage
- research alignment

---

## Example Output

```json
{
  "overall_match": 68,
  "core_ml_skills": 88,
  "mlops": 90,
  "production_systems": 85,
  "domain_alignment": 35,
  "ats_keyword_coverage": 65,
  "seniority_fit": 75
}
```

---

## Scoring Logic

Weight categories differently.

Example for Geospatial ML role:

| Category | Weight |
|---|---|
| Core ML Skills | 25% |
| Geospatial Domain | 25% |
| MLOps | 15% |
| Production Experience | 15% |
| ATS Keywords | 10% |
| Research Alignment | 10% |

---

# 7. Gap Analysis Layer

## Purpose

Identify:
- missing requirements
- transferable strengths
- realistic improvements
- non-fakeable gaps

---

## Responsibilities

Classify gaps into:

- critical missing
- preferred missing
- transferable but implicit
- should not fake

---

## Example

```json
{
  "critical_missing": [
    "remote sensing",
    "satellite imagery"
  ],
  "transferable_but_not_explicit": [
    "computer vision",
    "distributed ML pipelines"
  ],
  "should_not_fake": [
    "SAR",
    "LIDAR"
  ]
}
```

---

# 8. Rewrite Decision Layer

## Purpose

Prevent unnecessary or harmful rewrites.

Most AI resume tools fail here.

---

## Core Principle

DO NOT rewrite strong technical bullets.

Many LLMs incorrectly convert:
- technical depth
- architecture detail
- measurable impact

into:
- generic recruiter fluff

which weakens resumes significantly.

---

## Responsibilities

Classify each bullet:

```json
{
  "bullet": "",
  "quality": "strong | acceptable | weak",
  "rewrite_needed": true,
  "reason": ""
}
```

---

## Rewrite Rules

### Strong Bullets
- preserve
- optionally optimize keywords slightly

### Acceptable Bullets
- improve clarity
- improve ATS alignment

### Weak Bullets
- rewrite aggressively

---

# 9. Rewrite Engine

## Purpose

Generate truthful and targeted tailoring suggestions.

---

## Responsibilities

Generate:
- headline suggestions
- summary suggestions
- bullet improvements
- keyword placement suggestions
- ATS optimization advice

---

## Important Rules

### Never Hallucinate

Never:
- invent tools
- invent projects
- invent domains
- invent experience

---

### Preserve Metrics

Always preserve:
- performance metrics
- speedups
- dataset sizes
- deployment scale

---

### Preserve Technical Depth

Avoid replacing:

```text
ONNX + Triton deployment
```

with:

```text
optimized AI systems
```

The second version is weaker.

---

# 10. Final Report Layer

## Purpose

Present results clearly to users.

---

## Recommended Sections

### Tailored Headline

### Tailored Summary

### Match Overview

### Score Breakdown

### Matched Skills

### Missing Skills

### Transferable Strengths

### Recommended Bullet Rewrites

### Skills Section Suggestions

### Recruiter Assessment

### Warning Flags

---

# Recommended Tech Stack (Actual)

| Component | Implementation |
|---|---|
| Resume Parsing | PyMuPDF |
| Resume Chunking | Regex-based deterministic chunker (`apps/api/app/modules/resume_tailor/chunker.py`) |
| JD Chunking | Regex-based deterministic chunker |
| Embeddings API | Jina v3 (primary) / Cohere (fallback) |
| Vector Storage | Redis (cache layer, not ANN DB) |
| Semantic Matching | NumPy cosine similarity (deterministic) |
| Scoring Engine | Python dict + weighted averaging (deterministic) |
| LLM (prose) | Groq Llama 3.3 70B (primary) / Cerebras (fallback) / HF (last resort) |
| Backend | FastAPI + asyncio |
| Cache | Upstash Redis (REST API) |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js (React) |
| Charts/UI | Recharts / Lucide icons |

---

# Processing Strategy (Implemented)

## Deterministic Layer

**Handled entirely in Python/NumPy without AI:**
- Chunking (resume + JD) via regex patterns
- Keyword extraction via token matching + curated phrase list
- Embedding lookup (outsource to API, not local model)
- Similarity matrix (NumPy, cosine product)
- Score breakdown (weighted average per category)
- Gap classification (low-confidence matches, missing keywords)
- Rewrite candidate selection (bullets in the rewrite band)
- Evidence linkage (per-requirement best match)

**Result:** `MatchResult` JSON with scores, matches, gaps — fully auditable, no hallucinations.

---

## LLM Layer

**Small, focused call ONLY for prose generation:**
- Input: deterministic `MatchResult` (scores, gaps, candidate bullets)
- Task: generate headline, summary, bullet rewrites, fit assessment
- Output: prose fields only
- Constraints: "Use ONLY information provided in the deterministic analysis. Do NOT recompute scores."

**Result:** prose fields merged with deterministic results → final response.

**Key insight:** The LLM is grounded in factual analysis. It cannot hallucinate evidence because it doesn't generate the evidence — it just reframes it.

---

# Important Design Philosophy

## Good Tailoring ≠ Keyword Stuffing

A good system:
- preserves credibility
- improves alignment
- surfaces transferable skills
- explains gaps honestly

A bad system:
- rewrites everything
- adds fake experience
- injects random keywords
- destroys technical specificity

---

# Example of Good vs Bad Rewrite

## Bad Rewrite

Original:

```text
Built ONNX + NVIDIA Triton inference deployment pipeline
```

AI Rewrite:

```text
Optimized AI deployment systems
```

This removes:
- tooling specificity
- engineering depth
- production credibility

---

## Good Rewrite

```text
Built ONNX + NVIDIA Triton deployment pipeline enabling 50–100× faster inference in production NLP workloads
```

This preserves:
- tools
- metrics
- deployment scale
- engineering ownership

---

# Future Improvements

Potential future additions:

- recruiter persona scoring
- company-specific tailoring
- LinkedIn optimization
- portfolio alignment
- interview question prediction
- salary fit estimation
- auto-generated cover letters
- multilingual tailoring
- career trajectory analysis

---

# Implementation Notes (vs. Original Plan)

## Simplifications

The original plan proposed 10 distinct layers. The actual implementation collapses to **4 core operations** for these reasons:

1. **Chunking & Matching (Sections 1–5 → 2 ops)**
   - Resume parser + JD parser are simple regex-based chunkers, not AI models. Combined with embedding lookup in a single deterministic matcher.
   - Why: fast, repeatable, no hallucinations. The semantic heavy lifting comes from embeddings, not separate "JD Parser" and "Semantic Matching" stages.

2. **External embeddings instead of local models (Section 4 → HTTP call)**
   - Don't bake torch + sentence-transformers into the image (saves 1.5GB, startup latency).
   - Instead, use free Jina v3 + Cohere APIs (1M tokens/month free).
   - Why: 0 infrastructure overhead, handles model updates server-side, reliably degradable.

3. **Scoring is deterministic, not per-stage (Section 6 → single `_compute_score_breakdown()`)**
   - No separate "Scoring Engine" step. Score breakdown is computed once from the similarity matrix + keyword overlap.
   - Why: one source of truth. Simpler, faster, auditable.

4. **Single LLM call instead of multi-stage (Sections 8–9 → `_generate_tailor_prose()`)**
   - Gap analysis is deterministic (missing keywords, low-confidence matches).
   - Rewrite candidates are pre-selected by the matcher (partial-band bullets).
   - LLM receives the analysis and generates only prose: headline, summary, rewrites, fit assessment.
   - Why: cheaper (1.2k output vs. 2.5k), faster (1s vs. 4s), more focused (LLM can't recompute scores and mess them up).

## Caching Strategy

- **Per-resume:** resume text + chunks + embeddings cached 30 days, keyed by `sha256(pdf_bytes)`.
  - Cost: ~1k tokens to Jina on first upload of a unique resume, then free forever.
- **Per-JD:** never cached. Each JD is unique. (~600 embedding tokens per tailor request.)
- **Analysis:** not cached (deterministic matcher is cheap, ~10ms).

## Graceful Degradation

When embeddings are unavailable:
1. Matcher falls back to keyword-only matching.
2. Response includes `degraded: true` to signal UI.
3. Score breakdown is derived entirely from keyword overlap.
4. Transferable strengths + critical gaps are empty (require embeddings to compute).
5. User still gets a usable report — just less nuanced.

## Performance Baseline

| Metric | Value |
|---|---|
| **First resume tailor** (parse + embed) | ~2–3s (Groq ~1.5s, embeddings ~0.3s, match/LLM ~1s) |
| **Repeat resume** (same PDF, new JD) | ~1–2s (skip resume parse/embed, just JD embed + match + LLM) |
| **LLM tokens per tailor** | ~600 embed + ~1.5k LLM = ~2.1k (was ~7k with single-prompt) |
| **Cost at 100 tailor/month** | ~4 USD (Groq free tier covers it; Jina ~$1.20) |

---

# Original Principle (Still True)

The system should behave like:
- an experienced technical recruiter
- combined with a senior ML engineer
- combined with an ATS parser

Not like:
- a generic text rewriting chatbot

**The actual implementation delivers this by** separating the *analysis* (deterministic, honest) from the *prose* (AI-generated, grounded in the analysis).
