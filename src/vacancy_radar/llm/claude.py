"""Claude API LLMProvider — native document-block citations for grounding.

M4 work. See shared/tool-use-concepts.md / structured-outputs docs for the
citations content-block pattern this will use once implemented.
"""

from vacancy_radar.llm.base import LLMProvider
from vacancy_radar.models import Report


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str = "claude-opus-5") -> None:
        self.model = model

    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[str],
        similar_vacancies: list[dict],
        filter_rules: str,
    ) -> Report:
        raise NotImplementedError("M4: implement Claude API call with native citations")
