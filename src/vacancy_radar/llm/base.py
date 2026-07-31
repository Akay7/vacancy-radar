"""LLMProvider interface — Claude and Ollama implementations plug in behind this.

Grounding is not optional: any implementation must only draft claims that trace
back to a retrieved bullet or filter rule (see Report.citations).
"""

from abc import ABC, abstractmethod

from vacancy_radar.models import Report


class LLMProvider(ABC):
    @abstractmethod
    def analyze(
        self,
        jd_text: str,
        experience_bullets: list[str],
        similar_vacancies: list[dict],
        filter_rules: str,
    ) -> Report:
        """Produce a grounded match report for a job description."""
        raise NotImplementedError
