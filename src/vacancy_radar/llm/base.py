"""Shared LLM-layer pieces: the domain error type, and a structural type for calling code to
depend on (specs/010-langchain-integration).

Generation itself goes through LangChain's `BaseChatModel` (`ChatAnthropic`/`ChatOllama`), not a
hand-rolled ABC with per-vendor request/response code — see `llm/claude.py`/`llm/ollama.py`.
`LLMProvider` here is a `typing.Protocol` (structural typing only, no `abstractmethod`/`ABC`
enforcement) purely so `api.py` has a stable type to hang its `Depends(get_llm_provider)`
annotations on; it is not itself a client and doesn't reimplement anything a chat model does.
"""

import base64
from datetime import date as date_type
from typing import Protocol

from langchain_core.messages import HumanMessage
from langchain_core.messages.content import create_image_block
from pydantic import BaseModel

from vacancy_radar.models import CandidateReport, DraftVacancyMetadata


class LLMProviderError(Exception):
    """Raised when the configured LLM backend is unreachable, misconfigured, or returns
    unusable output (FR-012)."""


class LLMProvider(Protocol):
    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[tuple[str, str]],
        filter_rules: str,
    ) -> CandidateReport: ...

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata: ...

    def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str: ...


class RawDraftVacancyMetadata(BaseModel):
    """The schema actually requested from the LLM for `draft_vacancy_metadata()` — `date` stays
    a plain string here, unlike the domain `DraftVacancyMetadata.date: date`, since the model
    may legitimately return `""` when no date is stated in the document/image; `date` itself
    can't accept that (a strict `date` type), so this stays a separate structured-output target,
    finalized via `finalize_draft()` below (preserves specs/006-vacancy-upload's original
    blank-date-defaults-to-today behavior, which happened before Pydantic validation in the
    pre-migration code and still must here)."""

    company: str
    position: str
    date: str


def finalize_draft(raw: RawDraftVacancyMetadata) -> DraftVacancyMetadata:
    date_str = raw.date or date_type.today().isoformat()
    return DraftVacancyMetadata(company=raw.company, position=raw.position, date=date_str)


def build_vision_message(prompt: str, image_bytes: bytes, image_media_type: str) -> HumanMessage:
    """One shared vision-message builder for both providers (specs/010-langchain-integration,
    research.md #1) — both `ChatAnthropic` and `ChatOllama` translate this exact standardized
    content-block shape into their own wire format correctly (verified directly against both
    packages), replacing what used to be two separately hand-built request shapes."""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    return HumanMessage(
        content=[
            create_image_block(base64=image_b64, mime_type=image_media_type),
            {"type": "text", "text": prompt},
        ]
    )
