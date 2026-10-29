"""Pure text-sanitization helpers for cover_letter — deliberately dependency-
free (no WeasyPrint, no AI provider imports) so this stays importable/testable
in isolation, same reason resume_tailor keeps its own rendering.py (the one
file in that module that imports WeasyPrint) separate from its AI/generation
logic.
"""

from __future__ import annotations

# Backstop for the generation prompt's "never use em/en dashes or non-standard
# hyphens" rule (CLAUDE.md: Don't use "—" everywhere in the code, replace
# with "-" or " " or "," based on the context) - a style instruction alone
# has repeatedly NOT been reliably honored by these models in this codebase
# (same lesson that led to response_format=json_object for structural rules
# elsewhere); this makes it a guarantee instead of a hope. Hit live: the
# model used U+2011 NON-BREAKING HYPHEN for compound words ("end-to-end"),
# visually near-identical to a plain hyphen but not the same character,
# which an em/en-dash-only replace never caught. Covers every dash-class
# character that isn't the plain ASCII hyphen already. Safe to apply
# per-chunk mid-stream since none of these are multi-codepoint sequences
# that could straddle a chunk boundary.
_DASH_CHARS = str.maketrans({
    "‐": "-",  # hyphen
    "‑": "-",  # non-breaking hyphen
    "‒": "-",  # figure dash
    "–": "-",  # en dash
    "—": "-",  # em dash
    "―": "-",  # horizontal bar
    "−": "-",  # minus sign
})


def strip_dashes(text: str) -> str:
    return text.translate(_DASH_CHARS)


def split_paragraphs(content: str) -> list[str]:
    """Split into paragraphs on blank lines - the generated letter uses
    blank-line-separated paragraphs, but a user who's hand-edited the text in
    the textarea might only have single newlines between them, so fall back
    to splitting on every line in that case rather than rendering one giant
    run-on paragraph."""
    blocks = [p.strip() for p in content.replace("\r\n", "\n").split("\n\n") if p.strip()]
    if len(blocks) <= 1:
        blocks = [p.strip() for p in content.split("\n") if p.strip()]
    return blocks
