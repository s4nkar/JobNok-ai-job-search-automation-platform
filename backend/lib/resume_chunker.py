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
    # ── English ────────────────────────────────────────────────────────────────
    (re.compile(r"(requirements?|qualifications?|must[-\s]?have|what\s+you'?ll?\s+need)", re.I), "requirement"),
    (re.compile(r"(preferred|nice[-\s]?to[-\s]?have|bonus|plus)", re.I), "requirement"),
    # Modern JD phrasing for candidate requirements
    (re.compile(r"(you'?ll?\s+thrive|ideal\s+candidates?|what\s+you\s+(bring|offer)|you\s+should\s+have|about\s+you\b)", re.I), "requirement"),
    (re.compile(r"(responsibilities|what\s+you'?ll?\s+do|about\s+the\s+role|your\s+role|duties|in\s+this\s+role\b)", re.I), "responsibility"),
    # Benefits / perks sections — classified as domain so they don't pollute
    # critical gaps or keyword extraction regardless of where they appear in the JD
    (re.compile(r"(###\s*benefits?|benefits?\s*:?$|perks?\s*:?$|what\s+we\s+offer|what\s+speaks|compensation)", re.I), "domain"),
    (re.compile(r"(about\s+(?!the\s+role|your\s+role|this\s+role|you\b)\w+|who\s+we\s+are|company\s+(overview|focus)|join\s+us\s+for)", re.I), "domain"),
    # ── German ────────────────────────────────────────────────────────────────
    # Responsibilities: "Deine Aufgaben", "Dein Aufgabenbereich", "Das erwartet dich"
    (re.compile(r"(deine?\s+aufgaben|aufgabenbereich|dein\s+(profil|aufgaben)|das\s+erwartet)", re.I), "responsibility"),
    # Requirements: "Das bringst du mit", "Dein Profil", "Anforderungen", "Was du mitbringst"
    (re.compile(r"(das\s+bringst\s+du|was\s+du\s+mitbringst|dein\s+profil|anforderungen|tech[-\s]?skills?|know[-\s]?how)", re.I), "requirement"),
    # Benefits / company info (German) — catch all common variants including "Das spricht für uns"
    (re.compile(r"(was\s+wir\s+(bieten|mitbringen|dir|euch)|wer\s+wir\s+sind|das\s+bieten\s+wir|unser\s+angebot|das\s+spricht\s+für)", re.I), "domain"),
]

# Sentinel lines that mark where tracker-appended metadata begins.
_JD_METADATA_SENTINEL = re.compile(
    r"^(role\s+signals\s*:|\[paste\s+or\s+add|•\s*matched\s+role\s+keywords)",
    re.I | re.MULTILINE,
)

# Where the real JD body begins — strip the title/location header above this.
_JD_BODY_START = re.compile(
    r"^(about\s+the\s+role|your\s+responsibilities|responsibilities|requirements?|"
    r"what\s+you|we\s+are\s+looking|the\s+role|job\s+description|overview|"
    r"company\s+focus|as\s+an?\s+\w+[\s,]|"
    # German body start markers
    r"deine?\s+aufgaben|das\s+bringst\s+du|anforderungen|wir\s+suchen)",
    re.I | re.MULTILINE,
)

# Where useful JD content ends — contact info, apply instructions, legal text,
# and company "About us" boilerplate. These ALWAYS come last and are safe to
# truncate because no candidate requirements ever follow them.
# NOTE: Benefits sections are NOT truncated here — some JDs place requirements
# after benefits. Benefits are handled by _JD_HEADER_PATTERNS (domain kind).
_JD_END_SENTINEL = re.compile(
    r"^(contact\s+(us|information|details?)|about\s+(us|the\s+company)|"
    r"apply\s+(now|online|here|today)|how\s+to\s+apply|please\s+apply|"
    r"to\s+apply|equal\s+opportunity|background\s+check|affirmative\s+action|"
    r"privacy\s+policy|we\s+are\s+committed|we\s+look\s+forward|"
    # German equivalents
    r"kontakt(\s+zu\s+uns)?|über\s+uns|so\s+bewirbst\s+du\s+dich|"
    r"bewirb\s+dich|impressum|datenschutz)",
    re.I | re.MULTILINE,
)


def clean_jd_text(text: str) -> str:
    """Strip tracker metadata, leading title/location lines, and end-of-JD boilerplate.

    Call this before keyword extraction as well as before chunking so both
    paths operate on the same cleaned text.
    """
    # Strip tracker metadata appended by the job tracker UI
    m = _JD_METADATA_SENTINEL.search(text)
    if m:
        text = text[: m.start()].strip()
    # Strip contact info / legal / apply boilerplate at the end
    m = _JD_END_SENTINEL.search(text)
    if m:
        text = text[: m.start()].strip()
    # Strip leading title/location lines before the JD body
    m = _JD_BODY_START.search(text)
    if m:
        text = text[m.start():]
    return text


def chunk_jd(text: str) -> list[Chunk]:
    """Split a job description into embeddable chunks.

    Strategy:
      - Detect requirement/responsibility/about sections.
      - Inside each, split on bullets OR on sentence boundaries when bullets
        aren't used (recruiters often paste prose-only JDs).
      - Default chunk kind is 'requirement' when no section is detected —
        better to over-classify as requirements than to drop signal.
    """
    text = clean_jd_text(text)

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
    _SECTION_MAP = {
        "requirement": "requirements",
        "responsibility": "responsibilities",
        "domain": "about",
    }
    # Some JDs inline content on the same header line: "Company focus: - As an AI..."
    # Check just the prefix before ":" when it's short enough to be a label.
    if ":" in line:
        prefix = line.split(":", 1)[0].strip()
        if len(prefix) <= 30 and not prefix.endswith("."):
            for pat, kind in _JD_HEADER_PATTERNS:
                if pat.search(prefix):
                    return kind, _SECTION_MAP[kind]  # type: ignore[return-value]
    # Standard check: short lines that look like section headers.
    if len(line) > 60 or line.endswith("."):
        return None
    for pat, kind in _JD_HEADER_PATTERNS:
        if pat.search(line):
            return kind, _SECTION_MAP[kind]  # type: ignore[return-value]
    return None


# Split on sentence-ending punctuation followed by a capital letter.
# Negative lookbehind for common abbreviations so "e.g. Pandas" and
# "i.e. Docker" don't get split mid-clause.
_SENTENCE_SPLIT = re.compile(r"(?<![A-Z])(?<!e\.g)(?<!i\.e)(?<!etc)(?<=[.!?])\s+(?=[A-Z])")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


# ── Shared ────────────────────────────────────────────────────────

def _normalize_line(line: str) -> str:
    # Collapse runs of whitespace, strip soft hyphens / NBSPs that PDF extractors
    # commonly emit.
    line = line.replace(" ", " ").replace("­", "")
    return re.sub(r"\s+", " ", line).strip()
