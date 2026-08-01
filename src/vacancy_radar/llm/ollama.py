"""Local Ollama LLMProvider — prompt-enforced JSON, validated post-hoc by grounding.py.

Ollama has no native citations feature and no schema-enforced structured output, so this
provider relies on the shared prompt's explicit JSON-shape instructions plus Ollama's own
`format: "json"` request flag, with one retry if the response isn't valid JSON. Grounding
itself is enforced identically to ClaudeProvider, by the shared `grounding.enforce()`
checkpoint in the /analyze route — not by anything provider-specific.
"""

import json

import httpx

from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.prompts import build_analyze_prompt
from vacancy_radar.models import CandidateReport

RETRY_INSTRUCTION = (
    "\n\nYour previous response was not valid JSON. Respond with ONLY the JSON object "
    "described above — no other text, no markdown code fences."
)


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "qwen3:8b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host

    def _chat(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
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
