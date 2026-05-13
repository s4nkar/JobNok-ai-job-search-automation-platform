"""Deterministic resume + JD chunker.

Splits raw extracted text into atomic chunks suitable for embedding. No AI —
pure regex and heuristics, so it's fast, free, and reproducible.

Each chunk carries:
    kind     — bullet | skill | summary | header | requirement | responsibility
    section  — best-guess section name (experience, projects, skills, ...)
    text     — the chunk text, cleaned

For matching, we don't care about perfect section detection — the embedding does
the semantic lifting. The chunker just needs to break long blobs into ~1 sentence
units so the (m, n) similarity matrix has enough resolution to surface specific
evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ChunkKind = Literal[
    "bullet", "skill", "summary", "header",
    "requirement", "responsibility", "domain",
]

# Section headers we recognise. Order matters for greedy "current section" tracking.
_RESUME_SECTION_PATTERNS = [
    (re.compile(r"^\s*(work\s+experience|professional\s+experience|experience|employment)\s*:?\s*$", re.I), "experience"),
    (re.compile(r"^\s*(projects?|personal\s+projects?|side\s+projects?)\s*:?\s*$", re.I), "projects"),
    (re.compile(r"^\s*(education|academic)\s*:?\s*$", re.I), "education"),
    (re.compile(r"^\s*(skills?|technical\s+skills?|technologies)\s*:?\s*$", re.I), "skills"),
    (re.compile(r"^\s*(summary|profile|about|objective)\s*:?\s*$", re.I), "summary"),
    (re.compile(r"^\s*(publications?|papers?)\s*:?\s*$", re.I), "publications"),
    (re.compile(r"^\s*(certifications?|certificates?)\s*:?\s*$", re.I), "certifications"),
    (re.compile(r"^\s*(languages?)\s*:?\s*$", re.I), "languages"),
]

# Lines that visually start a bullet. Covers Unicode bullets emitted by PDF text
# extractors plus common ASCII conventions.
_BULLET_PREFIXES = ("•", "●", "○", "▪", "■", "·", "-", "*", "—", "–")

# Drop pure noise lines (page numbers, dates-only, separators).
_NOISE_LINE = re.compile(r"^\s*([\-=_*•·]{3,}|page\s+\d+|\d+\s*/\s*\d+)\s*$", re.I)


@dataclass
class Chunk:
    kind: ChunkKind
    section: str
    text: str

    def as_dict(self) -> dict:
        return {"kind": self.kind, "section": self.section, "text": self.text}


def chunks_to_dicts(chunks: list["Chunk"]) -> list[dict]:
    return [c.as_dict() for c in chunks]


def chunks_from_dicts(raw: list[dict] | None) -> list["Chunk"]:
    if not raw:
        return []
    return [Chunk(kind=r.get("kind", "bullet"), section=r.get("section", ""), text=r.get("text", "")) for r in raw]


# ── Resume chunker ────────────────────────────────────────────────

def chunk_resume(text: str) -> list[Chunk]:
    """Split a raw resume text dump into embeddable chunks.

    Heuristics:
      - Track the current section by header lines.
      - Lines starting with a bullet glyph become 'bullet' chunks.
      - Inside 'skills' section, comma-separated lists are split into individual
        'skill' chunks (one per item).
      - The summary section is kept as a single chunk (semantic unit).
      - Other lines are absorbed into the previous chunk if they look like a
        bullet continuation (no leading capital + no period termination on
        the prior line), else emitted as their own chunk.
    """
    chunks: list[Chunk] = []
    section = "header"  # everything before the first known header
    pending_summary: list[str] = []

    lines = [_normalize_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not _NOISE_LINE.match(ln)]

    i = 0
    while i < len(lines):
        line = lines[i]

        # Section header?
        new_section = _detect_section(line)
        if new_section:
            _flush_summary(pending_summary, chunks)
            section = new_section
            i += 1
            continue

        # Skills section: explode comma-separated lists, keep "Category: a, b, c"
        # as one chunk per skill item (prefixed with category if present).
        if section == "skills":
            for skill in _split_skill_line(line):
                chunks.append(Chunk(kind="skill", section="skills", text=skill))
            i += 1
            continue

        # Summary section: accumulate, emit as one chunk at section change / EOF.
        if section == "summary":
            pending_summary.append(line)
            i += 1
            continue

        # Bullet line — strip the prefix.
        if _is_bullet_line(line):
            body = _strip_bullet_prefix(line)
            # Absorb wrapped continuation lines (no bullet, lowercase start, no
            # new section header).
            j = i + 1
            while j < len(lines) and _is_continuation(lines[j]):
                body += " " + lines[j]
                j += 1
            chunks.append(Chunk(kind="bullet", section=section, text=body.strip()))
            i = j
            continue

        # Non-bullet line in an experience/project/etc. section — treat as a
        # standalone chunk if it has enough content to embed.
        if len(line) >= 8:
            kind: ChunkKind = "summary" if section in ("header", "summary") else "bullet"
            chunks.append(Chunk(kind=kind, section=section, text=line))
        i += 1

    _flush_summary(pending_summary, chunks)
    return [c for c in chunks if c.text]


def _flush_summary(pending: list[str], chunks: list[Chunk]) -> None:
    if not pending:
        return
    chunks.append(Chunk(kind="summary", section="summary", text=" ".join(pending).strip()))
    pending.clear()


def _detect_section(line: str) -> str | None:
    for pat, name in _RESUME_SECTION_PATTERNS:
        if pat.match(line):
            return name
    return None


def _is_bullet_line(line: str) -> bool:
    return line.startswith(_BULLET_PREFIXES)


def _strip_bullet_prefix(line: str) -> str:
    # Strip one leading bullet glyph + optional whitespace.
    for prefix in _BULLET_PREFIXES:
        if line.startswith(prefix):
            return line[len(prefix):].lstrip()
    return line


def _is_continuation(line: str) -> bool:
    """A line is a wrap-continuation of the previous bullet if it doesn't start
    a new section, isn't itself a bullet, and starts with lowercase or punctuation.
    """
    if not line:
        return False
    if _is_bullet_line(line):
        return False
    if _detect_section(line):
        return False
    first = line[0]
    return first.islower() or first in ",;:)("


def _split_skill_line(line: str) -> list[str]:
    """Split a skills-section line into individual skill items.

    Patterns handled:
      'Languages: Python, TypeScript, SQL' → ['Languages — Python', 'Languages — TypeScript', ...]
      'Python, TypeScript, SQL'            → ['Python', 'TypeScript', 'SQL']
    """
    category = ""
    body = line
    if ":" in line:
        category, _, body = line.partition(":")
        category = category.strip()

    # Split on common separators.
    parts = re.split(r"[,;|/·•]+", body)
    items = [p.strip(" .-") for p in parts if p.strip(" .-")]

    if category:
        return [f"{category} — {it}" for it in items]
    return items


# ── JD chunker ────────────────────────────────────────────────────

_JD_HEADER_PATTERNS = [
    (re.compile(r"(requirements?|qualifications?|must[-\s]?have|what\s+you'?ll?\s+need)", re.I), "requirement"),
    (re.compile(r"(preferred|nice[-\s]?to[-\s]?have|bonus|plus)", re.I), "requirement"),  # treated as requirement; weighted lower downstream
    (re.compile(r"(responsibilities|what\s+you'?ll?\s+do|role|duties)", re.I), "responsibility"),
    (re.compile(r"(about|who\s+we\s+are|company)", re.I), "domain"),
]


def chunk_jd(text: str) -> list[Chunk]:
    """Split a job description into embeddable chunks.

    Strategy:
      - Detect requirement/responsibility/about sections.
      - Inside each, split on bullets OR on sentence boundaries when bullets
        aren't used (recruiters often paste prose-only JDs).
      - Default chunk kind is 'requirement' when no section is detected —
        better to over-classify as requirements than to drop signal.
    """
    chunks: list[Chunk] = []
    current_kind: ChunkKind = "requirement"
    current_section = "requirements"

    lines = [_normalize_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not _NOISE_LINE.match(ln)]

    buf_prose: list[str] = []

    def flush_prose():
        if not buf_prose:
            return
        joined = " ".join(buf_prose).strip()
        # Split on sentence boundaries for prose-only JDs.
        for sentence in _split_sentences(joined):
            if len(sentence) >= 10:
                chunks.append(Chunk(kind=current_kind, section=current_section, text=sentence))
        buf_prose.clear()

    for line in lines:
        # Section header?
        header_kind = _detect_jd_section(line)
        if header_kind:
            flush_prose()
            current_kind, current_section = header_kind
            continue

        if _is_bullet_line(line):
            flush_prose()
            body = _strip_bullet_prefix(line).strip()
            if len(body) >= 4:
                chunks.append(Chunk(kind=current_kind, section=current_section, text=body))
            continue

        buf_prose.append(line)

    flush_prose()
    return chunks


def _detect_jd_section(line: str) -> tuple[ChunkKind, str] | None:
    # Treat short lines that look like headers (title-cased, no period, short).
    if len(line) > 60 or line.endswith("."):
        return None
    for pat, kind in _JD_HEADER_PATTERNS:
        if pat.search(line):
            section = {
                "requirement": "requirements",
                "responsibility": "responsibilities",
                "domain": "about",
            }[kind]
            return kind, section  # type: ignore[return-value]
    return None


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


# ── Shared ────────────────────────────────────────────────────────

def _normalize_line(line: str) -> str:
    # Collapse runs of whitespace, strip soft hyphens / NBSPs that PDF extractors
    # commonly emit.
    line = line.replace(" ", " ").replace("­", "")
    return re.sub(r"\s+", " ", line).strip()
