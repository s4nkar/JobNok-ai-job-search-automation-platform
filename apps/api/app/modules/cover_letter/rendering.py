"""PDF export for a generated cover letter - Jinja + WeasyPrint, same stack
resume_tailor already uses (reused here, not a new dependency).

Deliberately does NOT modify the letter's content - no auto-inserted
salutation or signature block. Renders exactly what's in the editable
textarea on the frontend, so there's no risk of duplicating a greeting or
sign-off the user already typed themselves.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML as WeasyHTML

from app.modules.cover_letter.text import split_paragraphs

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)


async def render_pdf(content: str) -> bytes:
    html = _jinja_env.get_template("cover_letter.html").render(paragraphs=split_paragraphs(content))
    return await asyncio.to_thread(lambda: WeasyHTML(string=html).write_pdf())
