"""Pydantic schemas shared across the API and LLM providers."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

MatchBand = Literal["strong", "good", "weak", "poor"]


class VacancyRecord(BaseModel):
    """Minimum required shape of a vacancy folder's `vacancy.yaml`.

    Only the four fields needed for retrieval metadata (see retriever.py) are validated;
    any other fields from the maintainer's private schema pass through unvalidated.
    """

    model_config = ConfigDict(extra="allow")

    company: str
    position: str
    date: date
    outcome: str


class Citation(BaseModel):
    quote: str
    source_id: str


class Flag(BaseModel):
    label: str
    severity: str  # "red" | "green"
    reason: str


class SimilarVacancy(BaseModel):
    vacancy_id: str
    company: str
    position: str
    outcome: str
    similarity: float
    excerpt: str
    is_duplicate: bool


class DraftSentence(BaseModel):
    """One grounded sentence of the draft paragraph, paired with the citation that grounds it.

    Additive alongside `Report.draft_paragraph`/`citations` (specs/005-minimal-ui) so a UI can
    render each sentence next to its citation without re-deriving the pairing from two
    separately-ordered flat lists.
    """

    text: str
    citation: Citation


class Report(BaseModel):
    score: MatchBand
    flags: list[Flag]
    gaps: list[str]
    similar: list[SimilarVacancy]
    draft_paragraph: str
    draft_sentences: list[DraftSentence]
    citations: list[Citation]


class CandidateFlag(BaseModel):
    """A flag as the LLM proposed it — not yet checked against real source text."""

    label: str
    severity: str  # "red" | "green"
    reason: str
    quote: str
    source_id: str


class CandidateSentence(BaseModel):
    """One draft-paragraph sentence as the LLM proposed it, with its claimed source."""

    text: str
    quote: str
    source_id: str


class CandidateReport(BaseModel):
    """Raw LLM output for /analyze, before `grounding.enforce()` validates every citation."""

    match_band: MatchBand
    flags: list[CandidateFlag]
    gaps: list[str]
    draft_sentences: list[CandidateSentence]


class DraftVacancyMetadata(BaseModel):
    """LLM-proposed company/position/date for a newly uploaded vacancy document
    (specs/006-vacancy-upload) — reviewed and editable by the maintainer before anything is
    saved. No `outcome` field: an initial posting/offer document can't reflect an outcome that
    hasn't happened yet, so the maintainer always sets it directly (FR-003).
    """

    company: str
    position: str
    date: date
