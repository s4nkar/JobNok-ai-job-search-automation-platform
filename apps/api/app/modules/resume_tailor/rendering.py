"""Everything that shapes/renders cv_data for a human to look at: the template
registry, Jinja/WeasyPrint rendering, cv_data normalization, the profile
contact overlay, the tailoring overlay (patch-based prose merged onto a base
structured CV), and the photo SSRF guard. Zero LLM calls — see generation.py
for that half.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import re
import urllib.parse
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML as WeasyHTML

if TYPE_CHECKING:
    from app.modules.resume_tailor.generation import TailorProseResult

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), autoescape=True)

_BULLET_PREFIX = re.compile(r"^[\s•\-\*▪–]+")

# Private/link-local IP ranges that must not be fetched (SSRF guard)
_PRIVATE_NETS = re.compile(
    r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|127\.|169\.254\.|::1$|fc|fd)",
    re.IGNORECASE,
)


def safe_photo_url(url: str | None) -> str | None:
    """Return url only if it is a public https URL. Returns None otherwise."""
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return None
    host = parsed.hostname or ""
    if _PRIVATE_NETS.match(host):
        return None
    return url


TEMPLATE_REGISTRY: dict[str, dict] = {
    "standard":             {"label": "Standard",             "desc": "Clean, professional single-column layout",         "font": "Arial, sans-serif",          "columns": 1, "file": "template_standard.html"},
    "modern":               {"label": "Modern",               "desc": "Two-column layout with sidebar for contact info",   "font": "Arial, sans-serif",          "columns": 2, "file": "template_modern.html"},
    "creative":             {"label": "Creative",             "desc": "Timeline-based design with icons and visual elements","font": "Arial, sans-serif",         "columns": 1, "file": "template_creative.html"},
    "classic":              {"label": "Classic",              "desc": "Traditional format with clean typography",          "font": "Times New Roman, serif",     "columns": 1, "file": "template_classic_new.html"},
    "balanced":             {"label": "Balanced",             "desc": "Professional layout with clear section divisions",  "font": "Arial, sans-serif",          "columns": 1, "file": "template_balanced.html"},
    "minimalist":           {"label": "Minimalist",           "desc": "Clean, modern design with subtle borders and spacing","font": "system-ui, sans-serif",    "columns": 1, "file": "template_minimalist.html"},
    "professional":         {"label": "Professional",         "desc": "Executive-style layout with elegant formatting",    "font": "Arial, sans-serif",          "columns": 1, "file": "template_professional.html"},
    "corporate":            {"label": "Corporate",            "desc": "Two-column corporate layout with header contact section","font": "Arial, sans-serif",     "columns": 2, "file": "template_corporate.html"},
    "bold":                 {"label": "Bold",                 "desc": "Bold styling with clear hierarchy and modern design","font": "Arial, sans-serif",         "columns": 1, "file": "template_bold.html"},
    "slate":                {"label": "Slate",                "desc": "Two-column slate accent layout with modern contrast","font": "Arial, sans-serif",         "columns": 2, "file": "template_slate.html"},
    "professional_compact": {"label": "Professional Compact", "desc": "Centered header with ALL CAPS section titles and clean hierarchy","font": "Arial, sans-serif","columns": 1, "file": "template_professional_compact.html"},
    "executive":            {"label": "Executive",            "desc": "Two-column sidebar layout with details panel",      "font": "Arial, sans-serif",          "columns": 2, "file": "template_executive.html"},
    "insight":              {"label": "Insight",              "desc": "Executive sidebar layout with navy accents and reference cards","font": "Inter, sans-serif","columns": 2, "file": "template_insight.html"},
    "atelier":              {"label": "Atelier",              "desc": "Editorial two-column layout inspired by artisan portfolios","font": "Georgia, serif",      "columns": 2, "file": "template_atelier.html"},
    "elegant":              {"label": "Elegant",              "desc": "Refined single-column with accent separators and strong hierarchy","font": "Georgia, serif","columns": 1, "file": "template_elegant.html"},
    "aqua":                 {"label": "Aqua",                 "desc": "Two-column layout with a soft header band and clear sectioning","font": "Arial, sans-serif","columns": 2, "file": "template_aqua.html"},
    "lebenslauf":           {"label": "Lebenslauf (DE)",      "desc": "Traditional German CV with photo sidebar",          "font": "Arial, sans-serif",          "columns": 2, "file": "template_classic.html", "requires_photo": True},
}


def list_templates() -> list[dict[str, Any]]:
    """Template registry metadata, no internal file paths."""
    return [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "file"}} for k, v in TEMPLATE_REGISTRY.items()]


def normalize_cv_data(cv_data: dict) -> None:
    """Strip bullet prefixes and normalise skill items in-place."""
    for section_key in ("featured_project",):
        if cv_data.get(section_key) and isinstance(cv_data[section_key].get("bullets"), list):
            cv_data[section_key]["bullets"] = [
                _BULLET_PREFIX.sub("", b) for b in cv_data[section_key]["bullets"]
            ]
    for section_key in ("experience", "projects", "other_sections"):
        for entry in cv_data.get(section_key) or []:
            if isinstance(entry.get("bullets"), list):
                entry["bullets"] = [_BULLET_PREFIX.sub("", b) for b in entry["bullets"]]
    if cv_data.get("skills"):
        normalised = []
        for s in cv_data["skills"]:
            items = s.get("items")
            if isinstance(items, list):
                items = ", ".join(str(i).strip(" •·-–\t") for i in items if str(i).strip(" •·-–\t"))
            elif items is not None:
                items = str(items)
                items = re.sub(r"<[^>]+>", " ", items)
                lines = [ln.strip(" •·-–\t") for ln in items.splitlines() if ln.strip(" •·-–\t")]
                if len(lines) > 1:
                    items = ", ".join(lines)
                items = items.strip()
            if items:
                normalised.append({**s, "items": items})
        cv_data["skills"] = normalised


async def fetch_lebenslauf_photo_fields(profile: dict) -> dict[str, Any]:
    """Fetch+base64-encode the profile photo for the lebenslauf template's
    photo/DOB/nationality fields. No caching here — a caller on a hot path
    (preview, debounced every 1.5s) should wrap this in its own short-TTL
    cache; PDF/editor generation is rate-limited tightly enough not to need one."""
    photo_base64 = None
    safe_url = safe_photo_url(profile.get("cv_photo_url"))
    if safe_url:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(safe_url)
                if r.status_code == 200:
                    photo_base64 = base64.b64encode(r.content).decode()
        except Exception:
            pass
    return {
        "photo_base64": photo_base64,
        "date_of_birth": profile.get("date_of_birth"),
        "nationality": profile.get("nationality"),
    }


async def apply_profile_overlay(cv_data: dict, profile: dict, profile_headline: str, template_id: str) -> None:
    """Overlay authoritative profile contact fields onto cv_data in-place."""
    profile_name = (profile.get("full_name") or "").strip()
    if profile_name and " " in profile_name:
        cv_data["full_name"] = profile_name
    if not profile_headline and profile.get("job_title"):
        cv_data["job_title"] = profile["job_title"]
    cv_email = profile.get("cv_email") or profile.get("email")
    if cv_email:
        cv_data["email"] = cv_email
    if profile.get("phone"):
        cv_data["phone"] = profile["phone"]
    if profile.get("linkedin_url"):
        cv_data["linkedin"] = profile["linkedin_url"]
    if profile.get("github_url"):
        cv_data["github"] = profile["github_url"]
    if profile.get("website_url"):
        cv_data["website"] = profile["website_url"]
    if profile.get("work_authorization"):
        cv_data["work_authorization"] = profile["work_authorization"]
    if profile.get("address_city"):
        parts = [profile["address_city"]]
        if profile.get("address_country"):
            parts.append(profile["address_country"])
        cv_data["location"] = ", ".join(parts)

    cv_data["photo_base64"] = (
        (await fetch_lebenslauf_photo_fields(profile))["photo_base64"] if template_id == "lebenslauf" else None
    )
    cv_data["date_of_birth"] = profile.get("date_of_birth")
    cv_data["nationality"] = profile.get("nationality")


def apply_tailoring_overlay(base_cv_data: dict, prose: "TailorProseResult") -> dict:
    """Merge JD-specific tailoring prose onto a JD-agnostic structured CV.
    Pure Python, no LLM. Returns a new dict — base_cv_data is not mutated.

    prose.bullet_rewrites already carries resolved {original, improved} text
    pairs — the stable bullet_id -> chunk-index resolution happens once in
    generation.py at prose-generation time, not here.

    Known limitation: base_cv_data's bullets come from a SEPARATE structuring
    LLM pass over resume_text, not a literal copy of resume_chunks text — so
    matching here is still text-similarity, not guaranteed-exact. The stable
    bullet_id scheme (see generation.py) fixes "the LLM mis-transcribes the
    original bullet," it does not fully eliminate structuring-vs-chunk drift.
    """
    cv_data = copy.deepcopy(base_cv_data)

    if prose.profile_headline:
        cv_data["job_title"] = prose.profile_headline
    if prose.tailored_summary:
        cv_data["summary"] = prose.tailored_summary

    if prose.bullet_rewrites:
        rewrite_map = {r["original"]: r["improved"] for r in prose.bullet_rewrites}
        for section_key in ("experience", "projects", "other_sections"):
            for entry in cv_data.get(section_key) or []:
                bullets = entry.get("bullets")
                if not isinstance(bullets, list):
                    continue
                entry["bullets"] = [rewrite_map.get(b, b) for b in bullets]
        if cv_data.get("featured_project") and isinstance(cv_data["featured_project"].get("bullets"), list):
            cv_data["featured_project"]["bullets"] = [
                rewrite_map.get(b, b) for b in cv_data["featured_project"]["bullets"]
            ]

    if prose.implied_skills_to_add:
        skills = cv_data.get("skills") or []
        by_category = {s["category"].casefold(): s for s in skills if s.get("category")}
        for addition in prose.implied_skills_to_add:
            category = (addition.get("category") or "").strip()
            items = (addition.get("items") or "").strip()
            if not category or not items:
                continue
            existing = by_category.get(category.casefold())
            if existing:
                existing["items"] = f"{existing['items']}, {items}" if existing.get("items") else items
            else:
                new_entry = {"category": category, "items": items}
                skills.append(new_entry)
                by_category[category.casefold()] = new_entry
        cv_data["skills"] = skills

    return cv_data


def render_html(template_id: str, cv_data: dict) -> str:
    template_file = TEMPLATE_REGISTRY[template_id]["file"]
    tmpl = _jinja_env.get_template(template_file)
    return tmpl.render(**cv_data)


async def render_pdf(template_id: str, cv_data: dict) -> bytes:
    html_out = render_html(template_id, cv_data)
    return await asyncio.to_thread(lambda: WeasyHTML(string=html_out).write_pdf())
