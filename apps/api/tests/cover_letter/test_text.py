"""Unit tests for cover_letter.text — pure string helpers, no I/O, no
mocking needed, and deliberately no WeasyPrint dependency (see that module's
docstring for why it's split out from rendering.py)."""

from app.modules.cover_letter.text import split_paragraphs, strip_dashes


def test_strip_dashes_replaces_em_dash():
    assert strip_dashes("I led a team—shipping three launches—on time.") == \
        "I led a team-shipping three launches-on time."


def test_strip_dashes_replaces_en_dash():
    assert strip_dashes("Results: 50–50% improvement.") == "Results: 50-50% improvement."


def test_strip_dashes_replaces_non_breaking_hyphen():
    # Hit live: the model used U+2011 for compound words like "end-to-end" —
    # visually near-identical to a plain hyphen but a different character,
    # which an em/en-dash-only replace never caught.
    assert strip_dashes("end‑to‑end AI‑engineered") == "end-to-end AI-engineered"


def test_strip_dashes_replaces_every_dash_class_character():
    sample = "a‐b‑c‒d–e—f―g−h"
    assert strip_dashes(sample) == "a-b-c-d-e-f-g-h"


def test_strip_dashes_leaves_plain_hyphen_and_ordinary_text_unchanged():
    assert strip_dashes("A plain hyphen-ated word, unchanged.") == "A plain hyphen-ated word, unchanged."


def test_strip_dashes_handles_empty_string():
    assert strip_dashes("") == ""


def test_split_paragraphs_on_blank_lines():
    content = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    assert split_paragraphs(content) == [
        "First paragraph here.", "Second paragraph here.", "Third paragraph here.",
    ]


def test_split_paragraphs_falls_back_to_single_newlines():
    # A user who's hand-edited the textarea might only have single newlines
    # between paragraphs, not blank-line separation — falling back avoids
    # rendering one giant run-on paragraph.
    content = "Line one.\nLine two.\nLine three."
    assert split_paragraphs(content) == ["Line one.", "Line two.", "Line three."]


def test_split_paragraphs_handles_crlf_line_endings():
    content = "First paragraph.\r\n\r\nSecond paragraph."
    assert split_paragraphs(content) == ["First paragraph.", "Second paragraph."]


def test_split_paragraphs_strips_whitespace_and_drops_empty_blocks():
    content = "  First.  \n\n\n\n  Second.  "
    assert split_paragraphs(content) == ["First.", "Second."]


def test_split_paragraphs_single_paragraph_no_newlines():
    assert split_paragraphs("Just one paragraph, no line breaks at all.") == \
        ["Just one paragraph, no line breaks at all."]
