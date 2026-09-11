"""Deterministic resume -> CvDataSchema extraction.

The no-LLM fallback for generate_base_cv_data when every AI provider in the
chain is exhausted (CLAUDE.md's deferred "Phase 2" fallback). Quality is
lower than an LLM structuring pass — no prose normalization, experience is
one coarse bucket rather than split per job — but the editor stays usable
and the user can hand-fix fields instead of being blocked by a 500.

Reuses chunker.chunk_resume's section/bullet heuristics rather than
re-implementing section detection.
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.resume_tailor.chunker import chunk_resume
from app.modules.resume_tailor.schemas import validate_cv_data

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w%-]+", re.I)
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w%-]+", re.I)
_URL_RE = re.compile(r"https?://[\w.-]+\.[a-z]{2,}(?:/\S*)?", re.I)
# 2-4 capitalised words; middle segment may be a bare initial ("Jane Q Public").
_NAME_RE = re.compile(r"^[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]*){1,3}$")


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    return m.group(0).strip() if m else None


def build_base_cv_data_deterministic(resume_text: str) -> dict[str, Any]:
    """Best-effort structured CV from raw resume text using regex + the
    deterministic chunker. Always returns a schema-valid dict (via
    validate_cv_data) — never raises on thin or malformed input."""
    lines = [ln.strip() for ln in resume_text.splitlines() if ln.strip()]
    chunks = chunk_resume(resume_text)

    full_name = ""
    for ln in lines[:8]:
        if _NAME_RE.match(ln) and "@" not in ln and not any(c.isdigit() for c in ln):
            full_name = ln
            break

    website = None
    for url in _URL_RE.findall(resume_text):
        low = url.lower()
        if "linkedin.com" in low or "github.com" in low:
            continue
        website = url
        break

    # Prefer a chunk from an actual summary/profile section; the chunker also
    # emits the name/contact header block as kind="summary" section="header".
    summary = next(
        (c.text for c in chunks if c.kind == "summary" and c.section == "summary"),
        "",
    )

    exp_bullets = [c.text for c in chunks if c.kind == "bullet" and c.section == "experience"]
    experience = (
        [{"title": "Professional Experience", "company": "", "location": None, "period": "", "bullets": exp_bullets}]
        if exp_bullets else []
    )

    project_bullets = [c.text for c in chunks if c.kind == "bullet" and c.section == "projects"]
    projects = [{"name": "Projects", "tech": None, "bullets": project_bullets}] if project_bullets else []

    skills_by_cat: dict[str, list[str]] = {}
    for c in chunks:
        if c.kind != "skill":
            continue
        if " — " in c.text:
            cat, item = c.text.split(" — ", 1)
        else:
            cat, item = "Skills", c.text
        skills_by_cat.setdefault(cat.strip(), []).append(item.strip())
    skills = [{"category": cat, "items": ", ".join(items)} for cat, items in skills_by_cat.items() if items]

    edu_lines = [c.text for c in chunks if c.section == "education"]
    education = (
        [{"degree": edu_lines[0], "institution": "", "location": None, "period": "",
          "details": " ".join(edu_lines[1:]) or None}]
        if edu_lines else []
    )

    raw = {
        "full_name": full_name,
        "job_title": "",
        "location": "",
        "email": _first(_EMAIL_RE, resume_text) or "",
        "phone": _first(_PHONE_RE, resume_text),
        "github": _first(_GITHUB_RE, resume_text),
        "linkedin": _first(_LINKEDIN_RE, resume_text),
        "website": website,
        "summary": summary,
        "experience": experience,
        "education": education,
        "skills": skills,
        "projects": projects,
        "publications": [],
        "languages": [],
        "other_sections": [],
    }
    return validate_cv_data(raw)
