# Resume Tailoring Tool — System Architecture & Requirements

## Goal

Build a production-quality AI-powered resume tailoring system that:

- Understands resumes and job descriptions structurally
- Produces explainable ATS-style scoring
- Detects transferable skills intelligently
- Avoids generic AI fluff
- Preserves strong technical experience
- Generates truthful rewrite suggestions
- Mimics how strong recruiters actually evaluate candidates

This architecture intentionally separates:
- deterministic processing
- semantic understanding
- LLM reasoning

instead of relying on a single giant prompt.

---

# High-Level System Flow

```text
User Uploads Resume + Pastes JD
                ↓
        Input Guardrail Layer
                ↓
          Resume Parser
                ↓
             JD Parser
                ↓
        Embedding Generation
                ↓
         Semantic Matching
                ↓
           Scoring Engine
                ↓
          Gap Analysis
                ↓
      Rewrite Decision Layer
                ↓
          Rewrite Engine
                ↓
          Final Report UI
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

# Recommended Tech Stack

| Component | Recommendation |
|---|---|
| Resume Parsing | PyMuPDF / pdfplumber |
| Structured Extraction | LLM + Pydantic |
| Embeddings | OpenAI / BGE |
| Vector DB | pgvector / Qdrant |
| Semantic Search | cosine similarity |
| Backend | FastAPI |
| Queue | Celery / Redis |
| Storage | PostgreSQL |
| Frontend | Next.js |
| LLM Orchestration | LangGraph / LangChain |

---

# Recommended Processing Strategy

## Deterministic Layer

Use for:
- parsing
- extraction
- scoring
- matching
- validation
- evidence mapping

These should be stable and reproducible.

---

## LLM Layer

Use for:
- nuanced explanations
- rewrite suggestions
- recruiter-style reasoning
- summaries

The LLM should NOT own the entire pipeline.

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

# Final Principle

The system should behave like:
- an experienced technical recruiter
- combined with a senior ML engineer
- combined with an ATS parser

Not like:
- a generic text rewriting chatbot
