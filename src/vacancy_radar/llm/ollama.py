"""Local Ollama LLMProvider — prompt-enforced JSON, validated post-hoc by grounding.py.

Ollama has no native citations feature and no schema-enforced structured output, so this
provider relies on the shared prompt's explicit JSON-shape instructions plus Ollama's own
`format: "json"` request flag, with one retry if the response isn't valid JSON. Grounding
itself is enforced identically to ClaudeProvider, by the shared `grounding.enforce()`
checkpoint in the /analyze route — not by anything provider-specific.
"""

import base64
import json
from datetime import date

import httpx
from pydantic import ValidationError

from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.prompts import (
    build_analyze_prompt,
    build_draft_metadata_prompt,
    build_draft_metadata_vision_prompt,
)
from vacancy_radar.models import CandidateReport, DraftVacancyMetadata

RETRY_INSTRUCTION = (
    "\n\nYour previous response was not valid JSON. Respond with ONLY the JSON object "
    "described above — no other text, no markdown code fences."
)


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "qwen3:8b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host

    def _chat(self, prompt: str, images: list[str] | None = None) -> str:
        message: dict = {"role": "user", "content": prompt}
        if images:
            message["images"] = images
        try:
            response = httpx.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [message],
                    "stream": False,
                    "format": "json",
                },
                timeout=120.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(f"Ollama unreachable/misconfigured: {exc}") from exc
        return response.json()["message"]["content"]

    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[tuple[str, str]],
        filter_rules: str,
    ) -> CandidateReport:
        prompt = build_analyze_prompt(jd_text, experience_bullets, filter_rules)

        raw = self._chat(prompt)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raw = self._chat(prompt + RETRY_INSTRUCTION)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LLMProviderError(
                    "Ollama did not return valid JSON after one retry"
                ) from exc

        return CandidateReport.model_validate(data)

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        if image_bytes is not None:
            return self._draft_from_image(image_bytes)
        return self._draft_from_text(document_text)

    def _draft_from_text(self, document_text: str) -> DraftVacancyMetadata:
        prompt = build_draft_metadata_prompt(document_text)

        raw = self._chat(prompt)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raw = self._chat(prompt + RETRY_INSTRUCTION)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LLMProviderError(
                    "Ollama did not return valid JSON after one retry"
                ) from exc

        if not data.get("date"):
            data["date"] = date.today().isoformat()
        return DraftVacancyMetadata.model_validate(data)

    def _draft_from_image(self, image_bytes: bytes) -> DraftVacancyMetadata:
        """Vision-based drafting for image uploads (specs/007-vision-drafting) — no local OCR
        fallback exists, so any failure here surfaces to the caller as LLMProviderError."""
        prompt = build_draft_metadata_vision_prompt()
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        raw = self._chat(prompt, images=[image_b64])
        try:
            data = json.loads(raw)
            if not data.get("date"):
                data["date"] = date.today().isoformat()
            return DraftVacancyMetadata.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMProviderError(f"Ollama vision response was not usable: {exc}") from exc
