"""Shared, provider-agnostic grounding checkpoint (Constitution II, NON-NEGOTIABLE).

Neither LLMProvider is trusted to self-enforce grounding — every flag and draft-paragraph
sentence a provider proposes is checked here, against the actual retrieved source text,
before it can appear in a response. An ungroundable claim is silently dropped, never
surfaced (FR-008) — the rest of the report still gets built.
"""

import re
from dataclasses import dataclass, field

from vacancy_radar.models import CandidateReport, Citation, Flag


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _strip_source_prefix(quote: str, source_id: str) -> str:
    """Drop a leading "[source_id] " the model may have echoed back verbatim.

    The prompt displays each bullet as "[bullet-0] <text>" so the LLM can address it by id
    (llm/prompts.py); a model can reasonably "quote" the whole displayed line, prefix
    included, rather than parsing out just the content. Stripping this specific, known
    artifact is not a loosening of the grounding check on genuinely fabricated content —
    it only accounts for formatting we introduced ourselves.
    """
    stripped = quote.strip()
    prefix = f"[{source_id}]"
    if stripped.startswith(prefix):
        return stripped[len(prefix) :].strip()
    return quote


def _is_grounded(quote: str, source_id: str, sources: dict[str, str]) -> bool:
    source_text = sources.get(source_id)
    if not source_text or not quote.strip():
        return False
    quote = _strip_source_prefix(quote, source_id)
    return _normalize(quote) in _normalize(source_text)


@dataclass
class GroundedContent:
    flags: list[Flag] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    draft_paragraph: str = ""
    citations: list[Citation] = field(default_factory=list)


def enforce(candidate: CandidateReport, sources: dict[str, str]) -> GroundedContent:
    flags: list[Flag] = []
    citations: list[Citation] = []

    for candidate_flag in candidate.flags:
        if not _is_grounded(candidate_flag.quote, candidate_flag.source_id, sources):
            continue
        flags.append(
            Flag(
                label=candidate_flag.label,
                severity=candidate_flag.severity,
                reason=candidate_flag.reason,
            )
        )
        citations.append(Citation(quote=candidate_flag.quote, source_id=candidate_flag.source_id))

    sentences: list[str] = []
    for sentence in candidate.draft_sentences:
        if not _is_grounded(sentence.quote, sentence.source_id, sources):
            continue
        sentences.append(sentence.text)
        citations.append(Citation(quote=sentence.quote, source_id=sentence.source_id))

    return GroundedContent(
        flags=flags,
        gaps=candidate.gaps,
        draft_paragraph=" ".join(sentences),
        citations=citations,
    )
