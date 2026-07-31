"""Local Ollama LLMProvider — prompt-enforced citations, validated post-hoc.

M4 work. Since Ollama has no native citations feature, grounding must be
enforced by prompt (quote + bullet-ID) and checked after generation that
every quoted span actually appears in the source bullets.
"""

from vacancy_radar.llm.base import LLMProvider
from vacancy_radar.models import Report


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "qwen3:8b", host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host

    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[str],
        similar_vacancies: list[dict],
        filter_rules: str,
    ) -> Report:
        raise NotImplementedError("M4: implement Ollama call + post-hoc grounding validation")
