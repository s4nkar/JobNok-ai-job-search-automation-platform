"""Prompt content + version constants for resume-tailor's LLM calls.

Kept separate from generation.py so that file stays pure orchestration
(calling the LLM, parsing JSON, validating, caching) without ~150 lines of
prompt text interspersed. A version constant lives next to the prompt it
versions, since bumping one always means the other changed too.

Bumping any of the three version constants below forces a fresh cache key /
fresh get_or_create_session lookup (see cache.py/repository.py) — no manual
cache-busting code needed. This module intentionally keeps only the CURRENT
text of each prompt (not a historical registry of every past version) — git
history already answers "what did this prompt used to say"; the version
constants exist purely to invalidate caches on change, not to replay history.
"""

from __future__ import annotations

# Bumping any of these forces a fresh cache key / fresh get_or_create_session
# lookup — see cache.py and repository.py.
# v2: extract_keywords rewritten from an open "any capitalised word" regex +
# blocklist to a structural-shape + bounded tech allowlist, plus a wider
# REWRITE_BAND. Changes matched/missing keywords and rewrite candidates, so
# existing sessions must re-analyse.
# v3: chunk_jd no longer merges bare (unbulleted) list-style lines into one
# run-on chunk — hit live on a real JD where an entire section (~780 chars,
# 8+ distinct requirements) collapsed into a single chunk because none of its
# lines had a bullet glyph or ending punctuation, leaving critical_missing/
# transferable_strengths empty. Also added computer-vision/edge phrase terms.
# v4: (a) split lines with MULTIPLE bullets squashed onto one line with no
# newline between them ("item1• item2• item3" — another common job-board
# copy-paste artifact, hit live on a real JD); (b) clean_jd_text's body-start
# cut is now trusted only within a small absolute budget, not 66% of the
# text — it was discarding a real, signal-rich intro + an entire bullet
# section on a JD whose body-start marker happened to sit at 32% in; (c)
# domain's score weight is redistributed across the other categories when
# the JD has no chunk classified as "domain" at all, instead of flatly
# scoring it 0 and costing every such JD 15 points regardless of true fit.
# v5: chunk_resume no longer classifies a job-title+date-range line
# ("Software Engineer Feb 2023 - Oct 2023") as kind="bullet" — hit live: one
# landed in the rewrite band and got "patched" into a nonsense line that
# would have been inserted into the CV as if it were a real achievement.
# v6: the "what you bring" JD header pattern now handles the "you'll" contraction
# (matches "What you'll bring:", not just "What you bring"). Hit live: a JD using
# "What you'll bring:" never got its requirement bullets classified as kind="requirement",
# so they were excluded from keyword extraction, critical_missing, and
# transferable_strengths entirely, starving the downstream LLM assessment of the JD's
# actual core requirements (RAG, MCP, agentic workflows all went undetected).
# v7: two more gaps from the same JD. (a) extract_keywords now captures plural
# acronyms ("LLMs", "MCPs") - the acronym shape's word-boundary check broke on a
# trailing plural "s". (b) chunk_jd now splits section headers that a job board
# glued directly onto the following sentence with no whitespace ("Job
# requirementsWe're looking for...", "The RoleWe're hiring...") - those lines were
# too long for the per-line header check to ever recognise as headers, so their
# content silently fell into the "domain" bucket and was excluded from keyword
# extraction and gap analysis.
# v8: a JD using "→" as its bullet glyph (with items squashed onto one line, zero
# newlines) plus first/third-person phrasing ("What you'd actually be doing:",
# "What they're looking for:", "I'm hiring... They build...") hit three compounding
# gaps at once - hit live, this collapsed the ENTIRE JD body (all 11 real
# requirement/responsibility bullets) into a single unsplit "domain" chunk, zeroing
# out core_skills/responsibilities/seniority and leaving critical_missing/
# transferable_strengths empty. Fixed: (a) '→' added to the bullet-glyph sets;
# (b) the responsibility header pattern now covers "what you'd/you'll [actually]
# [be] doing"; (c) a new requirement pattern covers third-person "what they're/
# we're looking for" and "who you are" headers.
# v9: the regex chunker's header/bullet heuristics will always have a long tail of
# real-world JD formatting they don't recognise (v6/v7/v8 above are three different
# examples from the SAME session). Added a deterministic quality gate
# (chunker.py::jd_chunking_is_pathological) plus an LLM-based repair pass
# (generation.py::chunk_jd_with_llm_repair, gated by that check, output validated by
# validation.py::validate_llm_jd_chunks) that only fires when the regex result looks
# like this exact collapse signature - normal, well-formatted JDs never touch the LLM
# path and keep costing nothing.
# v10: three more gaps from a real JD, one of them systemic. (a) the requirement
# header pattern didn't cover "Required Skills & Experience" (only bare
# "requirements"), so an entire JD's real requirements section inherited
# "responsibility" kind from the preceding "Key Responsibilities" header and was
# completely invisible to critical_missing/transferable_strengths. (b) the benefits
# pattern didn't cover "What's on Offer" (only "what we offer"), so those bullets
# inherited "requirement" kind and polluted critical_missing with things like
# "Salary up to £75,000 depending on experience". (c) root cause of why (b)'s fix
# alone didn't work at first: the JD used a curly apostrophe (U+2019) in "What's",
# and every apostrophe-dependent pattern in this file (you'll, you'd, they're,
# what's) is written with a literal ASCII "'" - silently fails against curly/smart
# quotes, which Word/LinkedIn/many job boards emit by default. Fixed at the root
# instead of patching each pattern: chunker.py now normalizes curly quotes to ASCII
# upstream of every header/bullet regex (clean_jd_text for JD whole-text passes,
# _normalize_line for both chunkers' per-line passes).
# v11: "Skills, Knowledge and Expertise" (as a section wrapper) with "Essential" /
# "Desirable" sub-labels - a standard UK/Irish JD convention - wasn't recognised at
# all, so an entire requirements list (7 bullets: degree, production ML/GenAI
# experience, Python, GenAI/LLM/RAG/cloud exposure, etc.) inherited "responsibility"
# kind from the preceding "Key Responsibilities" header. Signature this time: zero
# requirement-kind chunks meant core_skills/seniority/responsibilities all collapsed
# to the exact same number (the responsibility-score fallback), and
# critical_missing/transferable_strengths came back completely empty - no gaps
# shown at all, not even a genuine one.
# v12: MatchResult gained grounded_missing_keywords (matcher.py::
# _find_grounded_missing_keywords) - a missing JD keyword whose sentence has a
# STRONG embedding match against a specific resume bullet is now traced as
# "terminology gap, here's the evidence" instead of just landing in the flat
# missing_keywords list with no distinction from a genuine capability gap. See
# PROSE_PROMPT_VERSION v11 for how the tailoring prompt uses this.
# v13: two more real-JD bugs, both ISOLATED/minor rather than a wholesale
# collapse - which matters, because it's why they went uncaught. (a) the bare
# "preferred" trigger in the requirement-header pattern matched anywhere as a
# substring, so a normal bullet like "Cloud experience (AWS preferred)" was
# read as a (contentless) header change and silently DROPPED - never became a
# chunk at all, not even a misclassified one. (b) closing flavor-text
# sentences ("This is not a research role.", "We're looking for builders.")
# inherited "requirement" kind by default and ended up as literal Critical
# Gaps bullets. Fixed the specific patterns (chunker.py: anchored
# preferred/bonus/plus to the whole line; added _NON_REQUIREMENT_SENTENCE_RE).
# But the bigger change here is architectural: chunk_jd_with_llm_repair
# (generation.py) is no longer gated behind jd_chunking_is_pathological - it's
# LLM-PRIMARY now, regex is just the fallback. A single dropped bullet or
# misclassified sentence out of twenty-plus chunks doesn't move that gate's
# AGGREGATE statistics enough to ever trigger, by construction - no threshold
# tuning fixes that, since the bug is invisible at the aggregate level it
# measures. Confirmed cheap regardless of provider (sub-cent per JD on any
# current Flash-class model) so the always-on cost is worth it for closing
# this entire class of failure instead of chasing it one regex pattern at a
# time.
MATCHER_VERSION = "matcher-v13"
# v3 switched these to tier="light" to dodge a reasoning model leaking
# chain-of-thought instead of JSON — didn't fully fix it (the OpenRouter
# fallback model leaked too, and the light model's own lower per-minute
# token ceiling made rate-limit failures more likely, not less). v4 reverts
# to tier="heavy" and adds response_format={"type": "json_object"} instead —
# a structural JSON constraint at the API level, not a model choice bet.
# v5: explicit rule against double-extracting a mixed "Additional
# Information"-style section into BOTH languages/relocation AND
# other_sections verbatim (hit live: the same content rendered twice under
# two section titles).
STRUCT_PROMPT_VERSION = "struct-v5"
# v6: implied_skills_to_add widened to also cover direct peer/alternative
# tools within an ecosystem the candidate already works in (LangGraph implied
# by hands-on LangChain), not just supporting libraries — it was coming back
# empty on real sessions, leaving missing keywords entirely unaddressed.
# v7: the widened prompt alone was NOT safe — measured live, the model
# started copying the ENTIRE missing-keywords list into implied_skills_to_add
# instead of genuinely reasoning about what's implied (suggested AWS
# SageMaker + Azure OpenAI off nothing but LangChain/RAG experience).
# validation.py::validate_implied_skills is now a hard deterministic filter
# on top of it; this bump invalidates any prose cached with the unfiltered
# (unsafe) list from v6.
# v8: matcher-v3's chunk_jd fix changes rewrite_candidates/transferable_
# strengths/critical_missing (the prose prompt's own input), so cached prose
# from a matcher-v2 analysis must not be reused.
# v9: tailored_summary validation failure now tries a sentence-level repair
# (drop only the offending sentence) before falling back to fully discarding
# the field — a weak-match JD often produced an otherwise well-grounded
# summary that mentioned one missing keyword in-line, which used to wipe the
# whole field back to the resume's untailored original.
# v10: matcher-v5's chunking/scoring fixes change the analysis this prompt is
# built from (rewrite_candidates, transferable_strengths, critical_missing) —
# cached prose from an older matcher analysis must not be reused.
# v11: new TERMINOLOGY GAPS block (matcher.py::_find_grounded_missing_keywords).
# Previously the prompt hard-banned EVERY missing keyword, including ones the
# candidate demonstrably already covers in different words (JD says "predictive
# analytics", resume says "predictive ML models") — the anti-hallucination
# grounding check treated "not literally in the original resume text" as
# equivalent to "fabricated," which blocked legitimate re-terminology the same
# as an actual invented claim. Grounded terms are now explicitly allowed, scoped
# to the specific evidence bullet that justifies each one; ungrounded missing
# keywords stay banned exactly as before. validation.py's grounding check now
# accepts an allowlist of these terms — see validate_text_against_resume's
# extra_grounded_keywords_cf parameter.
PROSE_PROMPT_VERSION = "prose-v11"


JD_TRANSLATE_SYSTEM_PROMPT = (
    "Translate the following job description to English. "
    "CRITICAL: Preserve ALL original line breaks, bullet points, and list structure exactly — "
    "each item that was on its own line must remain on its own line after translation. "
    "If the text contains the SAME content in BOTH German AND English already, "
    "output ONLY the English version — do NOT translate the German again or duplicate any section. "
    "Preserve all technical terms, tool names, company names, and section headers exactly. "
    "Return only the translated text with no commentary or preamble."
)


STRUCT_SYSTEM_PROMPT = """You are a professional CV writer. Parse the resume text into a structured JSON object.

CRITICAL RULES — violating any of these produces a broken CV:
1. full_name: Extract the COMPLETE name (e.g. "Sankar Dev Santhosh", NOT just "Sankar"). Never truncate.
2. skills: For EVERY skill category, populate "items" as a non-empty comma-separated string of the actual tools/skills listed. NEVER leave "items" as null, empty string, or an empty list.
3. languages: Copy language entries EXACTLY as written in the resume. Do NOT substitute, add, or remove languages.
4. Completeness: Include ALL experience entries, ALL projects, ALL publications found in the resume. Do not omit any.
5. bullets: Each string in ANY bullets array MUST NOT start with a bullet character (•, -, *, ▪, –). The template adds its own markers. Strip any such prefix before including the text.
6. publications venue: Preserve the COMPLETE venue string verbatim, including any ranking qualifiers (e.g. "Q1-ranked", "Scopus indexed", "SJR"). Never truncate the venue name.
7. featured_project: If the resume contains a section labelled "FEATURED PROJECT", "HIGHLIGHT PROJECT", or similar, you MUST extract it into the `featured_project` field. NEVER leave featured_project null if the resume shows one. Do NOT duplicate it in the `projects` array.
8. other_sections: The categories above (experience/education/skills/projects/publications/languages) don't cover every possible resume section. If the resume has a section that doesn't fit any of them (e.g. "Volunteering", "Patents", "Certifications", "Awards", "References"), put it in `other_sections` with its ORIGINAL heading preserved verbatim. Do NOT drop it, and do NOT force it into an unrelated category above.
9. No double extraction: a resume section is often MIXED (e.g. one "Additional Information" block containing both a language list AND a relocation/availability line). Split it: the language list goes ONLY into `languages`, a relocation/visa/availability statement goes ONLY into `relocation` — NEVER also copy that same content into `other_sections`, even under the section's original heading. `other_sections` is for content left over AFTER languages/relocation/every other named field has taken its part — if nothing is left over, do not emit an entry for that section at all.

Return ONLY this JSON structure (no markdown, no extra text):
{
  "full_name": "string — complete name",
  "job_title": "string — headline/tagline",
  "location": "string (City, Country)",
  "email": "string",
  "phone": "string or null",
  "github": "string or null (path only, e.g. github.com/user)",
  "linkedin": "string or null (path only, e.g. linkedin.com/in/user)",
  "website": "string or null",
  "work_authorization": "string or null",
  "summary": "string — professional summary paragraph",
  "featured_project": {
    "name": "string", "year": "string or null", "tech": "string or null",
    "bullets": ["string"], "results": "string or null"
  },
  "experience": [
    {"title": "string", "company": "string", "location": "string or null",
     "period": "string", "bullets": ["string"]}
  ],
  "education": [
    {"degree": "string", "institution": "string", "location": "string or null",
     "period": "string", "details": "string or null"}
  ],
  "skills": [
    {"category": "string", "items": "SINGLE STRING — skills separated by commas, e.g. \\"Python, PyTorch, Docker\\". NOT an array. NEVER null or empty."}
  ],
  "projects": [
    {"name": "string", "tech": "string or null", "bullets": ["string"]}
  ],
  "publications": [
    {"title": "string", "venue": "string", "year": "string or null"}
  ],
  "languages": ["string — exact language entries from resume"],
  "relocation": "string or null",
  "other_sections": [
    {"heading": "string — the section's ORIGINAL heading from the resume, e.g. \\"Volunteering\\"", "bullets": ["string"]}
  ]
}"""


TAILOR_PROSE_SYSTEM_PROMPT = """You are a CV tailoring assistant. The deterministic ATS analysis is already done —
you receive its results and must NOT recompute scores, matched keywords, or missing keywords.

Return ONLY valid JSON in this shape:
{
  "target_role": "<job title from the JD>",
  "target_company": "<company name from the JD>",
  "profile_headline": "<headline in the format: [target job title] | [relevant skill] | [relevant skill] | [relevant skill] — use the exact target job title from the JD as the first segment, then 2–3 skills from the resume most relevant to this specific role>",
  "tailored_summary": "<professional summary paragraph — see tone rules below>",
  "bullet_patches": [{"bullet_id": "<EXACT id shown in brackets in REWRITE CANDIDATES, e.g. b12>", "improved": "<sharpened framing>"}],
  "implied_skills_to_add": [{"category": "<a skills category name matching how this resume already labels its skills>", "items": "<comma-separated foundational tools implied by the candidate's existing tech stack>"}],
  "summary": "<1-paragraph honest fit assessment noting strengths and real gaps>"
}

TERMINOLOGY GAPS vs MISSING KEYWORDS — read this before writing anything:
A TERMINOLOGY GAP means the candidate's resume ALREADY contains the evidence shown — it's just worded differently than the JD. You MAY use that exact JD term, but ONLY when you are writing about (rewriting a bullet_patch for, or referencing in tailored_summary) that SPECIFIC evidence — never attach it to unrelated experience, and never use more than one per sentence unless several are genuinely about that same evidence. This is correcting terminology for something real, not adding a new skill — treat it as allowed, not as a "missing keyword" needing to be worked around.
A MISSING KEYWORD (no terminology gap listed for it) has NO grounded evidence anywhere in the resume. Never use it under any framing, no matter how plausible it would sound.

Hard rules:
- bullet_patches: ONLY patch bullets from the REWRITE CANDIDATES list. Echo the EXACT bullet_id shown in brackets — do NOT retype the original bullet text.
  * PRESERVE every number, percentage, and metric from the original
  * NEVER add tools, methods, or domains absent from the original, UNLESS it's a TERMINOLOGY GAP term whose evidence bullet is THIS bullet_id — then using that exact term is allowed
  * Adjust only verb / framing / emphasis — the evidence must stay identical
- implied_skills_to_add: from the MISSING KEYWORDS list, add an item ONLY when it is a close sibling of something the candidate demonstrably already uses — either (a) a standard supporting library for their existing stack (Pandas/NumPy implied by hands-on PyTorch/ML work), or (b) a direct peer/alternative tool within the SAME ecosystem as one they already use (LangGraph or LlamaIndex implied by hands-on LangChain experience; Docker Compose implied by Docker). Group under a category name matching this resume's own skills section labelling.
  NEVER add: a different vendor's managed platform for something the resume already covers a different way (e.g. AWS SageMaker/Bedrock when the resume only shows direct OpenAI API use), a tool from a domain the resume shows no evidence of, or anything requiring dedicated infrastructure/training the resume doesn't demonstrate. When genuinely unsure, leave it out — omission is always safer than a claim the candidate can't defend in an interview.
  Leave empty if nothing qualifies.
- profile_headline: lead with the exact job title from the JD, then 2–3 of the candidate's REAL skills most relevant to THIS SPECIFIC ROLE. Prefer specific technical skills (e.g. RAG, NLP, LangChain, Transformers, EU AI Act) over generic acronyms — NEVER use "AI", "ML", or "Machine Learning" as a standalone headline segment; they are redundant when the job title already implies them. Draw from MATCHED KEYWORDS, TERMINOLOGY GAP terms, and resume skills when they clearly overlap the JD's domain. Never add skills the resume doesn't show, and never use a MISSING KEYWORD.
- tailored_summary TONE AND CONTENT — strict CV style, not cover letter style:
  * Write in NOMINATIVE STYLE ONLY — no pronouns at all. Do NOT use "I", "my", "their", "they", "this candidate", "the candidate". Start directly with a noun phrase: "Applied AI Engineer with 3+ years…".
  * NO cover-letter phrases: "I am confident", "I am excited", "I look forward to", "I believe".
  * NO vague filler: "drive innovation", "leveraging expertise", "improve complex workflows", "passionate about".
  * Lead with years of experience and core specialty, e.g. "Applied AI Engineer with 3+ years of experience building..."
  * Include at least ONE specific achievement from the resume (a metric, a project name, or a publication). Make it feel like THIS candidate, not any AI engineer.
  * Reframe genuine transferable experience for this specific role. Never claim domain expertise the resume does not show.
  * Write in your own words — do NOT copy or paraphrase sentence fragments from the JD requirements. The summary must read as the candidate's own story, not a reflection of the job posting.
  * A TERMINOLOGY GAP term may appear here ONLY when the sentence is describing that term's specific evidence (see the TERMINOLOGY GAPS explanation above).
  * NEVER mention any skill from the MISSING KEYWORDS list — those have no grounded evidence anywhere in the resume.
- summary: ground the fit assessment in the provided CRITICAL GAPS and TRANSFERABLE STRENGTHS.
- Return ONLY valid JSON, no markdown fences."""


# v1: first version. Only invoked as a repair path when
# chunker.py::jd_chunking_is_pathological flags the regex chunker's output as a
# likely collapse (see MATCHER_VERSION v9's note) - bump this if the prompt text
# changes in a way that could change chunk boundaries/kinds.
JD_CHUNK_PROMPT_VERSION = "jdchunk-v1"

JD_CHUNK_SYSTEM_PROMPT = """You segment a job description into typed chunks for a resume-matching system. You do NOT rewrite, summarise, or paraphrase anything - every chunk's "text" must be copied EXACTLY, character for character, from the source, or it will be discarded by a downstream verbatim check.

CRITICAL RULES:
1. Split the JD into individual requirement / responsibility / company-context statements - roughly one bullet point or one sentence per chunk. Do not merge multiple distinct asks into one chunk, even if the source text has no line break between them (job boards often strip formatting, gluing several bullet items onto one line with no separator between them).
2. "text" must be an EXACT verbatim substring of the source - same words, same punctuation, same casing, no added or removed words. No summarising, no combining two source bullets into one, no fixing typos.
3. Classify each chunk's "kind":
   - "requirement": a qualification, skill, or experience the candidate must have (years of experience, tools, "you should have...", "what they're looking for", bonus / nice-to-have items).
   - "responsibility": a task or activity the role involves day to day ("what you'll do", "you'll be...", "you'd be...").
   - "domain": company background, culture, funding, customers, benefits, or anything that isn't a specific ask of the candidate.
4. Cover the ENTIRE source text - do not skip sentences. If a sentence doesn't clearly fit requirement/responsibility, classify it "domain" rather than omitting it.
5. Do not invent chunks that aren't in the source text, and do not output the same sentence twice.

Return ONLY this JSON shape, no markdown fences:
{"chunks": [{"kind": "requirement" | "responsibility" | "domain", "text": "<verbatim source substring>"}]}"""
