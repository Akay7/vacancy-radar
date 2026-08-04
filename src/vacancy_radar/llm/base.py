"""The LLM layer: one `LLMProvider` class wrapping whichever `BaseChatModel` the caller
constructs (`ChatAnthropic` or `ChatOllama`), instead of a per-vendor subclass each
reimplementing the same request/response handling (specs/010-langchain-integration).

Every generation path — analyze, vacancy-metadata drafting (text and vision), and vision text
extraction — is built the same way: a `RunnableLambda` that turns the call's arguments into a
prompt/message, piped (`|`) into the chat model stage, invoked as one chain via `.invoke(dict)`.
Text prompts use `ChatPromptTemplate` (llm/prompts.py) inside that lambda; vision prompts build
a `HumanMessage` directly, since there's no dynamic text to template — either way the resulting
chain shape is identical, so all four paths compose and invoke the same way.

`api.py`'s `get_llm_provider()` is the only place that decides *which* chat model to build —
this class doesn't special-case a vendor anywhere: `.with_structured_output()`/`.with_retry()`/
`.invoke()` are all `BaseChatModel`/`Runnable` interface, identical regardless of backend. The
handful of vendor-specific exception types (`anthropic.APIError`, `httpx.HTTPError`) are caught
together since only one of them can ever actually fire for a given wrapped chat model — listing
both costs nothing and keeps this the one place backend failures are normalized to
`LLMProviderError`.
"""

import base64
from datetime import date as date_type

import anthropic
import httpx
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.messages.content import create_image_block
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

from vacancy_radar.llm.prompts import (
    ANALYZE_PROMPT,
    DRAFT_METADATA_PROMPT,
    analyze_prompt_input,
    build_draft_metadata_vision_prompt,
    build_extract_document_text_vision_prompt,
    draft_metadata_prompt_input,
)
from vacancy_radar.models import CandidateReport, DraftVacancyMetadata

_BACKEND_ERRORS = (anthropic.APIError, httpx.HTTPError)


class LLMProviderError(Exception):
    """Raised when the configured LLM backend is unreachable, misconfigured, or returns
    unusable output (FR-012)."""


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
    """One shared vision-message builder — both `ChatAnthropic` and `ChatOllama` translate this
    exact standardized content-block shape into their own wire format correctly (verified
    directly against both packages, research.md #1)."""
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    return HumanMessage(
        content=[
            create_image_block(base64=image_b64, mime_type=image_media_type),
            {"type": "text", "text": prompt},
        ]
    )


class LLMProvider:
    """Generation for /analyze, vacancy-metadata drafting, and vision-based text extraction —
    entirely in terms of the `BaseChatModel` interface, so this one class serves any backend
    `get_llm_provider()` hands it."""

    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model

    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[tuple[str, str]],
        filter_rules: str,
    ) -> CandidateReport:
        chain = ANALYZE_PROMPT | self._structured(CandidateReport)
        return self._invoke(chain, analyze_prompt_input(jd_text, experience_bullets, filter_rules))

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        if image_bytes is not None:
            assert image_media_type is not None  # always set together with image_bytes
            chain = self._vision_message(build_draft_metadata_vision_prompt()) | self._structured(
                RawDraftVacancyMetadata
            )
            raw = self._invoke(
                chain, {"image_bytes": image_bytes, "image_media_type": image_media_type}
            )
        else:
            chain = DRAFT_METADATA_PROMPT | self._structured(RawDraftVacancyMetadata)
            raw = self._invoke(chain, draft_metadata_prompt_input(document_text))
        return finalize_draft(raw)

    def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str:
        """Vision-based text extraction for image analysis (specs/009-analyze-and-log-vacancy)
        — plain text out, not structured output: unlike draft/analyze, this isn't validated
        against a schema."""
        chain = self._vision_message(build_extract_document_text_vision_prompt()) | self._chat_model
        response = self._invoke(
            chain, {"image_bytes": image_bytes, "image_media_type": image_media_type}
        )
        return response.content

    @staticmethod
    def _vision_message(prompt: str) -> Runnable:
        return RunnableLambda(
            lambda inputs: [
                build_vision_message(prompt, inputs["image_bytes"], inputs["image_media_type"])
            ]
        )

    def _structured(self, schema: type) -> Runnable:
        return self._chat_model.with_structured_output(schema, method="json_schema").with_retry(
            retry_if_exception_type=(OutputParserException,), stop_after_attempt=2
        )

    @staticmethod
    def _invoke(chain: Runnable, input_: dict):
        try:
            return chain.invoke(input_)
        except OutputParserException as exc:
            raise LLMProviderError(
                "LLM did not return usable structured output after one retry"
            ) from exc
        except _BACKEND_ERRORS as exc:
            raise LLMProviderError(f"LLM backend unreachable/misconfigured: {exc}") from exc
