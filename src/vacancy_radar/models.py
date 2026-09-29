"""The vault domain model: Vacancy, Document, Company, and their enums.

These types define the shape every later stage reads and writes. See
design.md for why the conditional `applied_date` rule is a model-level
validator, why `company_slug` is stored rather than computed, and why
dates are `date` rather than `datetime`.
"""

from datetime import date, datetime
from enum import StrEnum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

UNKNOWN_ROLE = "unknown"
"""The single sentinel for a role that could not be determined."""


class Status(StrEnum):
    """A vacancy's stage in the application pipeline.

    `FOUND` is the pre-application state: spotted, not yet applied to.
    """

    FOUND = "found"
    APPLIED = "applied"
    SCREENING = "screening"
    TAKE_HOME = "take_home"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"

    @classmethod
    def _missing_(cls, value: object) -> "Status | None":
        if isinstance(value, str):
            lowered = value.strip().lower()
            for member in cls:
                if member.value == lowered:
                    return member
        return None


_PIPELINE_ORDER: tuple[Status, ...] = (
    Status.FOUND,
    Status.APPLIED,
    Status.SCREENING,
    Status.TAKE_HOME,
    Status.INTERVIEW,
    Status.OFFER,
)
"""The active-pipeline order `STATUS_TRANSITIONS` is built from. Forward
movement means "later in this tuple", not "the immediate next member"
- a real pipeline skips `take_home` or jumps straight from `screening`
to `offer` often enough that only requiring *some* later stage, not
strictly the next one, is the useful rule."""

TERMINAL_STATUSES: frozenset[Status] = frozenset({Status.REJECTED, Status.GHOSTED})
"""Reachable, without `force`, from any active pipeline status - but
having no un-forced follow-on status of their own (see
`STATUS_TRANSITIONS`)."""


def _build_status_transitions() -> "dict[Status, frozenset[Status]]":
    transitions: dict[Status, frozenset[Status]] = {}
    for index, status in enumerate(_PIPELINE_ORDER):
        later_stages = frozenset(_PIPELINE_ORDER[index + 1 :])
        transitions[status] = later_stages | TERMINAL_STATUSES
    for status in TERMINAL_STATUSES:
        transitions[status] = frozenset()
    return transitions


STATUS_TRANSITIONS: "dict[Status, frozenset[Status]]" = _build_status_transitions()
"""The permitted status graph, as data - see design.md decision 5.
`STATUS_TRANSITIONS[current]` is the set of statuses reachable from
`current` without `force`. `set_status` (core.py) does nothing more
than look this up; no transition rule branches on status names inside
that function. A same-status call is a no-op handled by `set_status`
itself, not encoded here - no status maps to itself."""


class DocumentKind(StrEnum):
    """The kind of document attached to a vacancy."""

    POSTING = "posting"
    EMAIL = "email"
    NOTE = "note"
    TAKEHOME = "takehome"


class Vacancy(BaseModel):
    """A single job vacancy and its application state.

    `id` is immutable and sourced from frontmatter — never from a
    file's path, so it stays stable across renames (see `ids.py`).
    """

    id: str
    company: str
    company_slug: str
    role: str
    status: Status
    found_date: date

    source_url: str | None = None
    """Optional - some sources (a recruiter's PDF attachment, with no
    posting link) have no URL at all. Validated as http/https only
    when a value is given (see optional-vacancy-url change's
    design.md)."""
    applied_date: date | None = None

    stage_note: str | None = None
    salary_note: str | None = None
    recruiter: str | None = None
    external_id: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("source_url")
    @classmethod
    def _validate_source_url_scheme(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if urlparse(value).scheme not in ("http", "https"):
            msg = "source_url must be an http or https URL"
            raise ValueError(msg)
        return value

    @field_validator("role")
    @classmethod
    def _validate_role_non_empty(cls, value: str) -> str:
        if not value.strip():
            msg = "role must not be empty or whitespace-only"
            raise ValueError(msg)
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def role_is_placeholder(self) -> bool:
        return self.role.strip().lower() == UNKNOWN_ROLE

    @model_validator(mode="after")
    def _check_date_coherence(self) -> "Vacancy":
        if self.found_date > datetime.now().astimezone().date():
            msg = "found_date must not be in the future"
            raise ValueError(msg)
        if self.applied_date is not None and self.applied_date < self.found_date:
            msg = "applied_date must not be earlier than found_date"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _check_applied_date_matches_status(self) -> "Vacancy":
        """Enforce the conditional applied_date rule.

        This needs both `status` and `applied_date` in scope at once,
        so it is a model-level validator, not a field constraint on
        `applied_date` alone. See design.md.
        """
        if self.status is Status.FOUND:
            if self.applied_date is not None:
                msg = "applied_date must be absent when status is 'found'"
                raise ValueError(msg)
        elif self.applied_date is None:
            msg = f"applied_date is required when status is '{self.status}'"
            raise ValueError(msg)
        return self


def _vacancy_sort_key(vacancy: Vacancy) -> date:
    """A vacancy's effective sort date: applied_date, or found_date for
    `found`-status vacancies (which have no applied_date)."""
    return vacancy.applied_date or vacancy.found_date


def sort_vacancies(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Sort vacancies by applied_date descending (found_date for `found`
    rows), stable for ties."""
    return sorted(vacancies, key=_vacancy_sort_key, reverse=True)


class Document(BaseModel):
    """A single document (posting, email, note, take-home) attached to
    a vacancy."""

    id: str
    vacancy_id: str
    kind: DocumentKind
    title: str
    date: date
    external_id: str | None = None


class Company(BaseModel):
    """A company a vacancy belongs to."""

    slug: str
    name: str
    domains: list[str] = Field(default_factory=list)
    recruiters: list[str] = Field(default_factory=list)
    notes: str | None = None
