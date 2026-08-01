"""Shared prompt + JSON schema for /analyze — used by both ClaudeProvider and OllamaProvider.

One prompt, one schema, so both backends produce the same CandidateReport shape and are
held to the same grounding rules (Constitution III) before grounding.py's shared validator
checks their output (Constitution II).
"""

RUBRIC = """\
Assess the match across four dimensions:
1. Required skills present — does the candidate's real experience cover what the posting asks for?
2. Experience-level match — is the seniority/scope of their work comparable to what's expected?
3. Domain/industry match — has the candidate worked in a similar domain or on similar problems?
4. Evidenced impact — do their bullets show measurable outcomes, not just responsibilities?

Based on all four, classify the overall match as exactly one of:
"strong", "good", "weak", "poor"."""

CANDIDATE_REPORT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "match_band": {"type": "string", "enum": ["strong", "good", "weak", "poor"]},
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "severity": {"type": "string", "enum": ["red", "green"]},
                    "reason": {"type": "string"},
                    "quote": {"type": "string"},
                    "source_id": {"type": "string"},
                },
                "required": ["label", "severity", "reason", "quote", "source_id"],
                "additionalProperties": False,
            },
        },
        "gaps": {"type": "array", "items": {"type": "string"}},
        "draft_sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "quote": {"type": "string"},
                    "source_id": {"type": "string"},
                },
                "required": ["text", "quote", "source_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["match_band", "flags", "gaps", "draft_sentences"],
    "additionalProperties": False,
}


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
