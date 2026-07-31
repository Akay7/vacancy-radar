"""Pydantic schemas shared across the API and LLM providers."""

from pydantic import BaseModel


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
    title: str
    outcome: str
    similarity: float


class Report(BaseModel):
    score: float
    flags: list[Flag]
    gaps: list[str]
    similar: list[SimilarVacancy]
    draft_paragraph: str
    citations: list[Citation]
