"""LLMProvider interface — Claude and Ollama implementations plug in behind this.

Grounding is not optional, but it isn't this interface's job to enforce it: a provider
returns its best-effort CandidateReport, and the shared `grounding.enforce()` checkpoint
(specs/003-analyze-report-generation/research.md) — applied uniformly to every provider's
output in the /analyze route — is what actually decides which claims survive into the
response. `similar_vacancies` isn't an LLM input: Report.similar is populated directly from
retrieval, since a similar-vacancy fact isn't a valid citation source (only a bullet or a
filter rule is, per Constitution II) and there's nothing for the LLM to ground it in.
"""

from abc import ABC, abstractmethod

from vacancy_radar.models import CandidateReport, DraftVacancyMetadata


class LLMProviderError(Exception):
    """Raised when the configured LLM backend is unreachable or misconfigured (FR-012)."""


class LLMProvider(ABC):
    @abstractmethod
    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[tuple[str, str]],
        filter_rules: str,
    ) -> CandidateReport:
        """Produce a candidate report for a job description — not yet grounding-validated."""
        raise NotImplementedError

    @abstractmethod
    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        """Propose company/position/date from an uploaded vacancy document.

        The maintainer reviews and edits every field before anything is saved
        (specs/006-vacancy-upload) — this is a best-effort draft, not a validated fact.

        `image_bytes`/`image_media_type` are set together for image uploads
        (specs/007-vision-drafting) — `document_text` is always "" in that case, since local
        OCR has been removed; the image itself is read directly by the LLM. When set, the
        implementation MUST attempt vision-based drafting and raise `LLMProviderError` on any
        failure (no vision support, backend error, malformed output) rather than falling back
        to a text-based attempt — there is no OCR text to fall back to.
        """
        raise NotImplementedError
