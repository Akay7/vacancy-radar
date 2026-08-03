"""Claude API LLMProvider — structured JSON output, validated post-hoc by grounding.py.

Uses output_config.format for a schema-guaranteed CandidateReport rather than Anthropic's
native document-citations feature: the two are mutually incompatible (citations can't be
combined with output_config.format), and a structured multi-field report is worth more here
than native citation metadata — see specs/003-analyze-report-generation/research.md.
"""

import base64
import json
from datetime import date

import anthropic
from pydantic import ValidationError

from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.prompts import (
    CANDIDATE_REPORT_JSON_SCHEMA,
    DRAFT_METADATA_JSON_SCHEMA,
    build_analyze_prompt,
    build_draft_metadata_prompt,
    build_draft_metadata_vision_prompt,
)
from vacancy_radar.models import CandidateReport, DraftVacancyMetadata


class ClaudeProvider(LLMProvider):
    def __init__(
        self, model: str = "claude-opus-5", client: anthropic.Anthropic | None = None
    ) -> None:
        self.model = model
        self._client = client or anthropic.Anthropic()

    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[tuple[str, str]],
        filter_rules: str,
    ) -> CandidateReport:
        prompt = build_analyze_prompt(jd_text, experience_bullets, filter_rules)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                output_config={
                    "format": {"type": "json_schema", "schema": CANDIDATE_REPORT_JSON_SCHEMA}
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except (anthropic.APIConnectionError, anthropic.AuthenticationError) as exc:
            raise LLMProviderError(f"Claude API unreachable/misconfigured: {exc}") from exc

        text = next(block.text for block in response.content if block.type == "text")
        return CandidateReport.model_validate(json.loads(text))

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        if image_bytes is not None:
            return self._draft_from_image(image_bytes, image_media_type)
        return self._draft_from_text(document_text)

    def _draft_from_text(self, document_text: str) -> DraftVacancyMetadata:
        prompt = build_draft_metadata_prompt(document_text)

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                output_config={
                    "format": {"type": "json_schema", "schema": DRAFT_METADATA_JSON_SCHEMA}
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except (anthropic.APIConnectionError, anthropic.AuthenticationError) as exc:
            raise LLMProviderError(f"Claude API unreachable/misconfigured: {exc}") from exc

        text = next(block.text for block in response.content if block.type == "text")
        return self._parse_draft(text)

    def _draft_from_image(
        self, image_bytes: bytes, image_media_type: str | None
    ) -> DraftVacancyMetadata:
        """Vision-based drafting for image uploads (specs/007-vision-drafting) — no local OCR
        fallback exists, so any failure here surfaces to the caller as LLMProviderError."""
        prompt = build_draft_metadata_vision_prompt()
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                output_config={
                    "format": {"type": "json_schema", "schema": DRAFT_METADATA_JSON_SCHEMA}
                },
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": image_media_type,
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Claude vision request failed: {exc}") from exc

        text = next(block.text for block in response.content if block.type == "text")
        try:
            return self._parse_draft(text)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMProviderError(f"Claude vision response was not usable: {exc}") from exc

    def _parse_draft(self, text: str) -> DraftVacancyMetadata:
        data = json.loads(text)
        if not data.get("date"):
            data["date"] = date.today().isoformat()
        return DraftVacancyMetadata.model_validate(data)
