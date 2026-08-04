"""Shared prompt text for /analyze — used by both ClaudeProvider and OllamaProvider.

One prompt, so both backends produce the same CandidateReport shape and are held to the same
grounding rules (Constitution III) before grounding.py's shared validator checks their output
(Constitution II). The response shape itself is now enforced by passing the CandidateReport/
DraftVacancyMetadata Pydantic models directly to `with_structured_output()`
(specs/010-langchain-integration) rather than a hand-written JSON Schema dict passed alongside
the prompt.
"""

RUBRIC = """\
Assess the match across four dimensions:
1. Required skills present — does the candidate's real experience cover what the posting asks for?
2. Experience-level match — is the seniority/scope of their work comparable to what's expected?
3. Domain/industry match — has the candidate worked in a similar domain or on similar problems?
4. Evidenced impact — do their bullets show measurable outcomes, not just responsibilities?

Based on all four, classify the overall match as exactly one of:
"strong", "good", "weak", "poor"."""


def build_analyze_prompt(
    jd_text: str, bullets: list[tuple[str, str]], filter_rules_text: str
) -> str:
    bullets_block = (
        "\n".join(f"[{source_id}] {text}" for source_id, text in bullets)
        if bullets
        else "(none ingested)"
    )
    filter_rules_block = filter_rules_text.strip() or "(none provided)"

    return f"""\
You are assessing how well a candidate's real experience matches a job posting, using ONLY
the experience bullets and filter rules given below. Do not use any other knowledge about the
candidate — you have none.

# Job posting
{jd_text}

# Candidate's experience bullets (each tagged with its id)
{bullets_block}

# Candidate's filter rules (personal dealbreakers/preferences, if any)
{filter_rules_block}

# Rubric
{RUBRIC}

# Output rules (critical — every claim must be independently verifiable)
For every flag and every draft-paragraph sentence, you MUST include:
- "quote": the EXACT, VERBATIM text you are citing, copied character-for-character from one of
  the experience bullets above or the filter rules — do not paraphrase, summarize, or combine
  multiple bullets into one quote.
- "source_id": the id of the bullet you quoted from (e.g. "bullet-2"), or "filter-rules" if you
  quoted the filter rules.
Any flag or sentence whose quote cannot be found verbatim in its cited source will be discarded
before the user ever sees it — so only make claims you can back with an exact quote. "gaps" is
the one exception: list requirements from the posting that the bullets don't cover, as plain
statements of absence — no quote needed since these describe what's missing, not what's there.

Respond with ONLY a JSON object matching this shape (no other text):
{{
  "match_band": "strong" | "good" | "weak" | "poor",
  "flags": [
    {{"label": str, "severity": "red"|"green", "reason": str, "quote": str, "source_id": str}}
  ],
  "gaps": [str],
  "draft_sentences": [{{"text": str, "quote": str, "source_id": str}}]
}}"""


def build_draft_metadata_prompt(document_text: str) -> str:
    return f"""\
You are reading an uploaded job posting or offer document to help someone log it as a vacancy
record. Extract only what the document actually states — do not invent a company, position, or
date that isn't there.

# Document text
{document_text}

# Output rules
- "company": the hiring company's name, exactly as it appears in the document.
- "position": the job title/position, exactly as it appears in the document.
- "date": the posting or offer date, in YYYY-MM-DD format, if the document states one — an
  empty string "" if no date is stated. Do not guess a date that isn't in the document; the
  person reviewing this draft will fill in a date themselves if you leave it blank.
- Every field is reviewed and can be corrected by a person before it's saved — a reasonable
  best guess is fine, but never fabricate a specific value the document doesn't support; leave
  a field as an empty string "" instead.

Respond with ONLY a JSON object matching this shape (no other text):
{{
  "company": str,
  "position": str,
  "date": str
}}"""


def build_draft_metadata_vision_prompt() -> str:
    """Prompt for image uploads (specs/007-vision-drafting) — no OCR'd text is available;
    the model reads the attached image directly instead of any extracted text."""
    return """\
You are looking at an uploaded photo or screenshot of a job posting or offer, to help someone
log it as a vacancy record. Extract only what the image actually shows — do not invent a
company, position, or date that isn't legible in it.

# Output rules
- "company": the hiring company's name, exactly as it appears in the image.
- "position": the job title/position, exactly as it appears in the image.
- "date": the posting or offer date, in YYYY-MM-DD format, if the image shows one — an empty
  string "" if no date is legible. Do not guess a date that isn't shown; the person reviewing
  this draft will fill in a date themselves if you leave it blank.
- Every field is reviewed and can be corrected by a person before it's saved — a reasonable
  best guess is fine, but never fabricate a specific value the image doesn't support; leave a
  field as an empty string "" instead.

Respond with ONLY a JSON object matching this shape (no other text):
{
  "company": str,
  "position": str,
  "date": str
}"""


def build_extract_document_text_vision_prompt() -> str:
    """Prompt for the vision-based text extraction used only to drive retrieval for image
    uploads on the Analyze screen (specs/009-analyze-and-log-vacancy) — plain text out, no JSON
    wrapper, since this isn't validated against a schema like the other vision prompts."""
    return """\
You are looking at an uploaded photo or screenshot of a job posting. Transcribe its meaningful
content as plain text — the role, responsibilities, requirements, and any other substantive
details shown — so it can be used to search for relevant experience elsewhere. Do not add
commentary, headers, or formatting; just the posting's own content, as plain text. If the image
doesn't show a legible job posting, say so plainly in one short sentence instead of guessing."""
