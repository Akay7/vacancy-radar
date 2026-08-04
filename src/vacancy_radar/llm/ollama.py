"""Local Ollama LLMProvider — LangChain's ChatOllama (specs/010-langchain-integration).

`with_structured_output(schema, method="json_schema")` uses Ollama's own structured output API
(schema-enforced, not prompt-engineered `format: "json"`). It doesn't retry on its own, so the
retry-once-on-invalid-output behavior this provider has always had is reproduced via LangChain's
own `Runnable.with_retry()` composed on top — not a hand-rolled retry loop.
"""

import httpx
from langchain_core.exceptions import OutputParserException
from langchain_ollama import ChatOllama

from vacancy_radar.llm.base import (
    LLMProviderError,
    RawDraftVacancyMetadata,
    build_vision_message,
    finalize_draft,
)
from vacancy_radar.llm.prompts import (
    build_analyze_prompt,
    build_draft_metadata_prompt,
    build_draft_metadata_vision_prompt,
    build_extract_document_text_vision_prompt,
)
from vacancy_radar.models import CandidateReport, DraftVacancyMetadata


class OllamaProvider:
    def __init__(self, model: str = "qwen3:8b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host
        self._chat_model = ChatOllama(model=model, base_url=host)

    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[tuple[str, str]],
        filter_rules: str,
    ) -> CandidateReport:
        prompt = build_analyze_prompt(jd_text, experience_bullets, filter_rules)
        return self._structured_invoke(CandidateReport, prompt)

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        if image_bytes is not None:
            assert image_media_type is not None  # always set together with image_bytes
            prompt = build_draft_metadata_vision_prompt()
            message = build_vision_message(prompt, image_bytes, image_media_type)
            raw = self._structured_invoke(RawDraftVacancyMetadata, [message])
        else:
            prompt = build_draft_metadata_prompt(document_text)
            raw = self._structured_invoke(RawDraftVacancyMetadata, prompt)
        return finalize_draft(raw)

    def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str:
        """Vision-based text extraction for image analysis (specs/009-analyze-and-log-vacancy)
        — plain text out, not structured output."""
        prompt = build_extract_document_text_vision_prompt()
        message = build_vision_message(prompt, image_bytes, image_media_type)
        try:
            response = self._chat_model.invoke([message])
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama unreachable/misconfigured: {exc}") from exc
        return response.content

    def _structured_invoke(self, schema: type, input_):
        structured = self._chat_model.with_structured_output(
            schema, method="json_schema"
        ).with_retry(retry_if_exception_type=(OutputParserException,), stop_after_attempt=2)
        try:
            return structured.invoke(input_)
        except OutputParserException as exc:
            raise LLMProviderError("Ollama did not return valid JSON after one retry") from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama unreachable/misconfigured: {exc}") from exc
