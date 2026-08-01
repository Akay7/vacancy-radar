"""Pydantic schemas shared across the API and LLM providers."""

from datetime import date

from pydantic import BaseModel, ConfigDict


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


class Report(BaseModel):
    score: float
    flags: list[Flag]
    gaps: list[str]
    similar: list[SimilarVacancy]
    draft_paragraph: str
    citations: list[Citation]
