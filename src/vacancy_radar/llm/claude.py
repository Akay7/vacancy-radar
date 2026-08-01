"""Claude API LLMProvider — structured JSON output, validated post-hoc by grounding.py.

Uses output_config.format for a schema-guaranteed CandidateReport rather than Anthropic's
native document-citations feature: the two are mutually incompatible (citations can't be
combined with output_config.format), and a structured multi-field report is worth more here
than native citation metadata — see specs/003-analyze-report-generation/research.md.
"""

import json

import anthropic

from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.llm.prompts import CANDIDATE_REPORT_JSON_SCHEMA, build_analyze_prompt
from vacancy_radar.models import CandidateReport


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
