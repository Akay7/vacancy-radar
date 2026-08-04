"""Claude API LLMProvider — LangChain's ChatAnthropic (specs/010-langchain-integration).

`with_structured_output(schema, method="json_schema")` uses Claude's own dedicated structured
output feature — the same underlying mechanism the pre-migration `output_config.format` used —
so request/response handling (schema translation, parsing, validation) is ChatAnthropic's
responsibility now, not hand-written here.
"""

import anthropic
from langchain_anthropic import ChatAnthropic

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


class ClaudeProvider:
    def __init__(
        self, model: str = "claude-opus-5", chat_model: ChatAnthropic | None = None
    ) -> None:
        self.model = model
        self._chat_model = chat_model or ChatAnthropic(model=model)

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
        — plain text out, not structured output: unlike draft/analyze, this isn't validated
        against a schema."""
        prompt = build_extract_document_text_vision_prompt()
        message = build_vision_message(prompt, image_bytes, image_media_type)
        try:
            response = self._chat_model.invoke([message])
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Claude vision request failed: {exc}") from exc
        return response.content

    def _structured_invoke(self, schema: type, input_):
        structured = self._chat_model.with_structured_output(schema, method="json_schema")
        try:
            return structured.invoke(input_)
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Claude API unreachable/misconfigured: {exc}") from exc
