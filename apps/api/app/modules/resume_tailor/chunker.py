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
_BULLET_PREFIXES = ("•", "●", "○", "▪", "■", "·", "-", "*", "—", "–", "→")

# Drop pure noise lines (page numbers, dates-only, separators).
_NOISE_LINE = re.compile(r"^\s*([\-=_*•·]{3,}|page\s+\d+|\d+\s*/\s*\d+)\s*$", re.I)

# Bullet glyphs that are UNAMBIGUOUSLY list markers wherever they appear —
# unlike '-'/'*'/'—'/'–' (also legitimate mid-sentence punctuation: hyphens,
# em/en dashes, footnote asterisks), these never occur outside a list item,
# so it's safe to split on one even mid-line. '→' added after a real JD used
# it as an inline bullet glyph with zero newlines between items ("What you'd
# be doing:→ item one→ item two→ item three") - the whole block collapsed
# into one unsplit chunk and, since nothing recognised the header either,
# landed as "domain" instead of "responsibility", zeroing out the matcher's
# responsibility/core-skills scores entirely.
_UNAMBIGUOUS_BULLET_CHARS = "•●○▪■·→"
_INLINE_BULLET_SPLIT_RE = re.compile(f"(?=[{_UNAMBIGUOUS_BULLET_CHARS}])")


def _expand_inline_bullets(line: str) -> list[str]:
    """A single line can contain SEVERAL bullet items squashed together with
    no line break between them ("item one• item two• item three") — a common
    copy-paste artifact when a job board's <li> elements collapse into one
    text line with no newlines inserted. Every bullet-detection check here
    only looks at the START of a line, so a mid-line bullet glyph would
    otherwise get silently swallowed as trailing text of the first item (hit
    live: a 4-bullet "Required" block collapsed into one JD chunk with three
    embedded, unsplit "•" characters still in the text). Splits on every
    occurrence of an unambiguous bullet glyph, keeping it as the prefix of
    its own segment; a line with none is returned unchanged."""
    parts = [p.strip() for p in _INLINE_BULLET_SPLIT_RE.split(line) if p.strip()]
    return parts if len(parts) > 1 else [line]


def _expand_lines(lines: list[str]) -> list[str]:
    return [expanded for ln in lines for expanded in _expand_inline_bullets(ln)]


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
    lines = _expand_lines(lines)

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
            if section not in ("header", "summary") and _looks_like_title_or_company_line(line):
                # A job-title+date-range line ("Software Engineer Feb 2023 -
                # Oct 2023") or a company/location line — structural metadata,
                # not an achievement statement. kind="header" (not "bullet")
                # keeps it out of matcher.py's rewrite-candidate pool: hit
                # live, one of these landed in the rewrite band and the LLM
                # patched it into "Software Engineer Feb 2023 - Oct 2023 -
                # recent graduate with a Computer Science degree..." - a
                # nonsense line that would've been inserted into the CV.
                kind: ChunkKind = "header"
            else:
                kind = "summary" if section in ("header", "summary") else "bullet"
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


# An unambiguous date-RANGE shape ("2023 - 2025", "Feb 2023 - Oct 2023",
# "2024 - Present") — achievement bullets describe what was done, not when a
# role was held, so this shape essentially only appears on a job-title or
# project-period line, never inside real bullet content.
_TITLE_DATE_RANGE_RE = re.compile(
    r"((19|20)\d{2}|present)\s*[-–—]\s*((19|20)\d{2}|present|now)"
    r"|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(19|20)\d{2}",
    re.I,
)


def _looks_like_title_or_company_line(line: str) -> bool:
    """A job-title+date-range line ("Software Engineer Feb 2023 - Oct 2023")
    or similar structural header within an experience/project entry —
    metadata, not an achievement statement, so it shouldn't be eligible as a
    bullet-rewrite candidate (hit live: one of these landed in the matcher's
    rewrite band and got patched into a nonsense line that would have been
    inserted into the CV as if it were a real bullet). The 100-char cap
    avoids misclassifying a genuine (if unusually long) bullet that happens
    to mention a date range in passing."""
    return len(line) < 100 and bool(_TITLE_DATE_RANGE_RE.search(line))


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
    (re.compile(r"(requirements?|required\s+(skills?|experience|qualifications?)|"
                r"skills,?\s*knowledge\s+and\s+expertise|qualifications?|must[-\s]?have|what\s+you'?ll?\s+need)", re.I), "requirement"),
    # "preferred"/"bonus"/"plus" anchored to the WHOLE line - as bare substring
    # matches they silently ate real requirement bullets that happen to use one
    # of these words as ordinary content ("Cloud experience (AWS preferred)"),
    # classifying the bullet as a (contentless) header change and dropping it
    # entirely rather than misclassifying it - a worse failure than a wrong
    # kind label, since the content never becomes a chunk at all. "nice to have"
    # stays a substring search - a 3-word phrase, not a single common word, so
    # the collision risk is low.
    (re.compile(r"(^\s*(preferred|bonus|plus)\s*:?\s*$|nice[-\s]?to[-\s]?have)", re.I), "requirement"),
    # Bare "Essential" / "Desirable" as standalone lines - the standard UK/Irish
    # JD convention for sub-labelling a requirements list by priority. Anchored
    # to the WHOLE line for the same reason as "The Role" below - both words are
    # too generic to safely match as a substring mid-sentence.
    (re.compile(r"^\s*(essential|desirable)\s*$", re.I), "requirement"),
    # Modern JD phrasing for candidate requirements
    (re.compile(r"(you'?ll?\s+thrive|ideal\s+candidates?|what\s+you'?ll?\s+(bring|offer)|you\s+should\s+have|about\s+you\b)", re.I), "requirement"),
    # Third-person JD phrasing (a hiring manager writing "I'm hiring... They
    # build..." rather than addressing the candidate directly as "you").
    (re.compile(r"(what\s+(?:they|we)'?re\s+looking\s+for|who\s+you\s+are)", re.I), "requirement"),
    (re.compile(r"(responsibilities|what\s+you'?(?:d|ll)?\s+(?:actually\s+)?(?:be\s+)?do(?:ing)?\b|about\s+the\s+role|your\s+role|duties|in\s+this\s+role\b)", re.I), "responsibility"),
    # Bare "The Role" as a standalone line (common short-header phrasing).
    # Anchored to the WHOLE line, not a substring search like the patterns
    # above — "role" alone is too generic to safely match mid-sentence.
    (re.compile(r"^\s*the\s+role\s*$", re.I), "responsibility"),
    # Benefits / perks sections — classified as domain so they don't pollute
    # critical gaps or keyword extraction regardless of where they appear in the JD
    (re.compile(r"(###\s*benefits?|benefits?\s*:?$|perks?\s*:?$|what\s+we\s+offer|what'?s\s+on\s+offer|what\s+speaks|compensation)", re.I), "domain"),
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

# A cleaned JD shorter than this almost certainly means a heuristic below
# mis-fired and gutted the text — fall back to the uncleaned original.
_JD_MIN_USEFUL_LEN = 120

# Job-board copy-paste artifact: a section header glued directly onto the
# following sentence with zero whitespace, e.g. "Job requirementsWe're
# looking for engineers..." or "The RoleWe're hiring...". _detect_jd_section
# only classifies a line when the WHOLE line looks like a short header
# (<=60 chars, no trailing period) — a squashed header+paragraph line is far
# too long to ever be recognised as one. Splitting here, before line
# processing, gives the per-line header check a chance to see the header on
# its own line. The zero-width transition straight into a capitalised word is
# the tell: normal prose always has a space there, so this never fires on
# real running text.
_SQUASHED_HEADER_RE = re.compile(
    r"\b(about\s+the\s+job|the\s+role|job\s+requirements|"
    r"what\s+you'?(?:d|ll)?\s+(?:actually\s+)?(?:be\s+)?do(?:ing)?|"
    r"what\s+you'?ll?\s+(?:bring|need)|requirements|responsibilities|qualifications)"
    r"(?=[A-Z][a-z])",
    re.I,
)

# Some job boards glue the FOLLOWING header onto the END of the previous item
# instead ("...not through a ticket queueWhat they're looking for:→ 3+
# years...") - the opposite direction from the case above. Insert a newline
# BEFORE the header phrase when it's immediately preceded by a lowercase
# letter with no whitespace. Case-sensitive (capital "What") since "what" is
# far too common a lowercase word mid-sentence to safely split on.
_SQUASHED_HEADER_PRECEDED_RE = re.compile(
    r"(?<=[a-z])(What\s+(?:they|we)'?re\s+looking\s+for|"
    r"What\s+you'?(?:d|ll)?\s+(?:actually\s+)?(?:be\s+)?do(?:ing)?)"
)


def _split_squashed_headers(text: str) -> str:
    text = _SQUASHED_HEADER_RE.sub(lambda m: m.group(1) + "\n", text)
    text = _SQUASHED_HEADER_PRECEDED_RE.sub(lambda m: "\n" + m.group(1), text)
    return text

# Where useful JD content ends — contact info, apply instructions, legal text,
# and company "About us" boilerplate. Trusted ONLY when the match sits in the
# back portion of the text: "About us" / "we are committed to..." just as
# often OPEN a posting as a company blurb, and cutting there deletes the whole
# JD (hit live: a JD starting with "About Us" cleaned down to "").
# NOTE: Benefits sections are NOT truncated here — some JDs place requirements
# after benefits. Benefits are handled by _JD_HEADER_PATTERNS (domain kind).
_JD_END_SENTINEL = re.compile(
    r"^(contact\s+(us|information|details?)|about\s+(us|the\s+company)|"
    r"apply\s+(now|online|here|today)|how\s+to\s+apply|please\s+apply|"
    r"to\s+apply|equal\s+opportunity|background\s+check|affirmative\s+action|"
    r"privacy\s+policy|we\s+are\s+committed|we\s+look\s+forward|"
    # Common closing-CTA flourish in modern (esp. startup/consultancy) JDs —
    # "If you want to help shape X - we'd love to speak." Only trusted (like
    # every pattern here) in the back half of the text via the caller's guard.
    r"if\s+you\s+want\s+to\b|we'?d\s+love\s+to\s+(speak|talk|chat|hear)|get\s+in\s+touch|"
    # German equivalents
    r"kontakt(\s+zu\s+uns)?|über\s+uns|so\s+bewirbst\s+du\s+dich|"
    r"bewirb\s+dich|impressum|datenschutz)",
    re.I | re.MULTILINE,
)


def clean_jd_text(text: str) -> str:
    """Strip tracker metadata, leading title/location lines, and end-of-JD boilerplate.

    Call this before keyword extraction as well as before chunking so both
    paths operate on the same cleaned text.

    Every cut is guarded: an end sentinel is honoured only in the back half of
    the text, a body-start marker only in the front two-thirds, and if the
    result still comes out implausibly short the original text is returned
    untouched. A mis-fire that deletes the whole JD (→ 0 chunks → silent
    keyword-only degrade) is far worse than leaving a little boilerplate in.
    """
    # Normalized FIRST, before anything else below runs - every apostrophe-
    # dependent header pattern in this file (you'll, you'd, they're, what's)
    # is written with a literal ASCII "'" and silently fails to match a curly/
    # smart "'" (U+2019), which is extremely common (Word, LinkedIn, many job
    # boards). Hit live: "What's on Offer" (curly apostrophe) wasn't recognised
    # as a benefits header, so its bullets inherited "requirement" kind from
    # whatever section came before and polluted critical_missing/
    # transferable_strengths with things like "Salary up to £75,000".
    text = _normalize_quotes(text)
    original = text.strip()

    # Strip tracker metadata appended by the job tracker UI
    m = _JD_METADATA_SENTINEL.search(text)
    if m:
        text = text[: m.start()].strip()

    # Strip contact info / legal / apply / "about the company" boilerplate at
    # the FIRST such marker past the midpoint — an earlier match (common with
    # "About Us" / "we are committed to...") is an opening blurb, not the end.
    cut_at = next(
        (m.start() for m in _JD_END_SENTINEL.finditer(text) if m.start() >= len(text) * 0.5),
        None,
    )
    if cut_at is not None:
        text = text[:cut_at].strip()

    # Strip leading title/location lines before the JD body — this exists to
    # skip a short "Title \n Company · Location" header (always a couple
    # short lines, a few dozen chars), so the cut is trusted only within a
    # small ABSOLUTE budget, not a fraction of the JD's length. A percentage
    # threshold (tried previously: 66%) let the marker match deep into a long
    # JD and discard a real, signal-rich intro paragraph + an entire bullet
    # section along with it (hit live: "About the job" + "Why Join Us"
    # discarded because "Responsibilities" happened to appear at 32% in —
    # comfortably under 66%, but that content was the JD's real domain
    # signal, not a throwaway header).
    m = _JD_BODY_START.search(text)
    if m and m.start() <= min(200, len(text) * 0.15):
        text = text[m.start():]

    text = text.strip()
    return text if len(text) >= _JD_MIN_USEFUL_LEN else original


def _is_jd_continuation(line: str) -> bool:
    """A bare (non-bulleted) line is a wrap-continuation of the previous one
    only if it doesn't start a new section, isn't itself a bullet, and starts
    with lowercase or punctuation — mirrors chunk_resume's _is_continuation,
    JD-section-aware version."""
    if not line:
        return False
    if _is_bullet_line(line):
        return False
    if _detect_jd_section(line):
        return False
    first = line[0]
    return first.islower() or first in ",;:)("


def chunk_jd(text: str) -> list[Chunk]:
    """Split a job description into embeddable chunks.

    Strategy:
      - Detect requirement/responsibility/about sections.
      - Inside each, split on bullets, or on LINE boundaries for bare
        (unbulleted) list items — job boards routinely flatten "<li>" markup
        to plain newline-separated lines with no bullet glyph at all (hit
        live: a JD listing "Computer vision model development", "Edge AI and
        embedded vision systems", "Depth sensing and calibration" etc. as
        bare lines, none ending in sentence punctuation, collapsed into ONE
        779-char chunk — destroying the deterministic analysis's granularity:
        critical_missing/transferable_strengths came back empty and the
        prose model had almost no signal to reframe the summary around).
      - A line only merges into the previous chunk when it looks like a
        genuine wrap-continuation (starts lowercase/punctuation); a new
        capitalised line always starts a fresh chunk, whether or not it ends
        in a period.
      - Default chunk kind is 'requirement' when no section is detected —
        better to over-classify as requirements than to drop signal.
    """
    text = clean_jd_text(text)
    text = _split_squashed_headers(text)

    chunks: list[Chunk] = []
    current_kind: ChunkKind = "requirement"
    current_section = "requirements"

    lines = [_normalize_line(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln and not _NOISE_LINE.match(ln)]
    lines = _expand_lines(lines)

    buf_prose: list[str] = []

    def flush_prose():
        if not buf_prose:
            return
        joined = " ".join(buf_prose).strip()
        # Split on sentence boundaries within the buffered group (handles a
        # genuine multi-sentence prose paragraph); a bare list-style line with
        # no terminal punctuation survives as one chunk since there's no
        # split point to find.
        for sentence in _split_sentences(joined):
            if len(sentence) >= 10:
                k, s = _override_non_requirement_kind(sentence, current_kind, current_section)
                chunks.append(Chunk(kind=k, section=s, text=sentence))
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
                k, s = _override_non_requirement_kind(body, current_kind, current_section)
                chunks.append(Chunk(kind=k, section=s, text=body))
            continue

        # A new (non-continuation) bare line starts its own chunk rather than
        # silently merging with whatever's already buffered.
        if buf_prose and not _is_jd_continuation(line):
            flush_prose()
        buf_prose.append(line)

    flush_prose()
    return chunks


# kind -> canonical JD section name. Module-level (not a local of
# _detect_jd_section) so other code that needs to build a JD Chunk from a bare
# kind - e.g. validation.py's LLM-chunk-repair validator - shares the exact
# same mapping instead of re-declaring it.
JD_KIND_TO_SECTION: dict[str, str] = {
    "requirement": "requirements",
    "responsibility": "responsibilities",
    "domain": "about",
}


def _detect_jd_section(line: str) -> tuple[ChunkKind, str] | None:
    # Some JDs inline content on the same header line: "Company focus: - As an AI..."
    # Check just the prefix before ":" when it's short enough to be a label.
    if ":" in line:
        prefix = line.split(":", 1)[0].strip()
        if len(prefix) <= 30 and not prefix.endswith("."):
            for pat, kind in _JD_HEADER_PATTERNS:
                if pat.search(prefix):
                    return kind, JD_KIND_TO_SECTION[kind]  # type: ignore[return-value]
    # Standard check: short lines that look like section headers.
    if len(line) > 60 or line.endswith("."):
        return None
    for pat, kind in _JD_HEADER_PATTERNS:
        if pat.search(line):
            return kind, JD_KIND_TO_SECTION[kind]  # type: ignore[return-value]
    return None


# Split on sentence-ending punctuation followed by a capital letter.
# Negative lookbehind for common abbreviations so "e.g. Pandas" and
# "i.e. Docker" don't get split mid-clause.
_SENTENCE_SPLIT = re.compile(r"(?<![A-Z])(?<!e\.g)(?<!i\.e)(?<!etc)(?<=[.!?])\s+(?=[A-Z])")


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


# Stylistic role-framing / closing flavor text - "This is not a research
# role. We're looking for builders." - that carries no real ask and shouldn't
# be eligible for critical_missing/transferable_strengths regardless of which
# section it structurally lands under (hit live: these ended up as literal
# "Critical Gaps" bullets, as if not-being-a-research-role were a skill the
# candidate was missing). Deliberately narrow, anchored shapes only - this is
# NOT a general "is this really a requirement?" classifier (not tractable with
# regex) - each shape here hit live, verbatim or near-verbatim, on a real JD.
# "we're looking for builders." (ends right after ONE word) is safe to catch;
# "we're looking for engineers who want to..." (a real requirements lead-in
# elsewhere this session) has real content after "looking for" and is left
# alone by the trailing-word anchor.
_NON_REQUIREMENT_SENTENCE_RE = re.compile(
    r"^(this\s+is\s+not\s+a\s+.{0,30}?\s+role\b|we'?re\s+looking\s+for\s+\w+\.?\s*$)",
    re.I,
)


def _override_non_requirement_kind(text: str, kind: ChunkKind, section: str) -> tuple[ChunkKind, str]:
    if _NON_REQUIREMENT_SENTENCE_RE.match(text.strip()):
        return "domain", "about"
    return kind, section


# ── Shared ────────────────────────────────────────────────────────

# Curly/smart quotes -> ASCII. Every apostrophe-dependent regex in this file
# (you'll, you'd, they're, what's) is written with a literal ASCII "'" and
# won't match U+2019/U+2018 - common output from Word, LinkedIn, and other job
# boards. Normalizing once here, upstream of every pattern, beats hand-adding
# a curly-quote alternative to each regex individually (and reliably missing
# one - this session already found this exact gap one JD at a time).
_QUOTE_NORMALIZE_MAP = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
})


def _normalize_quotes(text: str) -> str:
    return text.translate(_QUOTE_NORMALIZE_MAP)


def _normalize_line(line: str) -> str:
    line = _normalize_quotes(line)
    # Collapse runs of whitespace, strip soft hyphens / NBSPs that PDF extractors
    # commonly emit.
    line = line.replace(" ", " ").replace("­", "")
    return re.sub(r"\s+", " ", line).strip()


# ── Chunking quality gate ────────────────────────────────────────────
# Still pure/deterministic, no AI here - this only DECIDES whether an LLM
# repair pass is worth attempting. The repair call itself lives in
# generation.py, which is where this module's "no AI" boundary stops
# applying (see its module docstring).

_PATHOLOGICAL_MIN_TEXT_LEN = 400
_PATHOLOGICAL_MAX_REQ_RESP_SHARE = 0.2
_PATHOLOGICAL_MAX_SINGLE_CHUNK_SHARE = 0.35


def jd_chunking_is_pathological(chunks: list[Chunk], source_text: str) -> bool:
    """Heuristic signature of the regex chunker's known failure mode: hit live
    twice on two different real JDs (a squashed "What you'll bring:" header,
    then a JD using arrow bullets + third-person phrasing) where a header
    phrasing the section regexes didn't recognise left almost the entire JD
    body misclassified as "domain" - which the matcher excludes from keyword
    extraction and gap analysis, and zeroes out core_skills/responsibilities/
    seniority scoring, while still returning a confident-looking overall
    score. Two independent tells, either one is enough:

      - requirement+responsibility content is a suspiciously small share of
        the JD (a real posting almost always spends most of its words on
        actual asks, not company blurb)
      - one single chunk holds a large share of all the text (a sign the
        line-splitting logic failed to break up a run-on block)

    Skipped entirely for short JDs - too little text for the share checks to
    be a meaningful signal rather than noise."""
    total_len = len(source_text)
    if total_len < _PATHOLOGICAL_MIN_TEXT_LEN:
        return False

    req_resp_len = sum(len(c.text) for c in chunks if c.kind in ("requirement", "responsibility"))
    max_chunk_len = max((len(c.text) for c in chunks), default=0)

    return (
        req_resp_len / total_len < _PATHOLOGICAL_MAX_REQ_RESP_SHARE
        or max_chunk_len / total_len > _PATHOLOGICAL_MAX_SINGLE_CHUNK_SHARE
    )
