"""Pure text helpers — dash-class normalization. No AI/DB imports, so this
stays trivially unit-testable (same isolation reasoning as cover_letter's
own text.py)."""

from __future__ import annotations

from typing import Any

_DASH_CHARS = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-", "−": "-",
})


def strip_dashes(text: str) -> str:
    return text.translate(_DASH_CHARS)


def strip_dashes_deep(value: Any) -> Any:
    """Recursively applies strip_dashes to every string in a nested
    dict/list structure. The generation prompt already instructs the model
    never to use em/en dashes, but a style instruction alone isn't reliably
    honored (the same lesson cover_letter's own strip_dashes backstop
    exists for) - this is the deterministic second layer over every
    free-text field in the LLM's JSON response (questions, answers, tips,
    role_assessment text)."""
    if isinstance(value, str):
        return strip_dashes(value)
    if isinstance(value, list):
        return [strip_dashes_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: strip_dashes_deep(v) for k, v in value.items()}
    return value
