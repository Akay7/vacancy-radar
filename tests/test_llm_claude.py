import json

import anthropic
import httpx
import pytest

from vacancy_radar.llm.base import LLMProviderError
from vacancy_radar.llm.claude import ClaudeProvider


class _TextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, content: list) -> None:
        self.content = content


class _FakeMessages:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._error:
            raise self._error
        return self._response


class _FakeClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.messages = _FakeMessages(response=response, error=error)


VALID_CANDIDATE_JSON = json.dumps(
    {
        "match_band": "good",
        "flags": [
            {
                "label": "Backend",
                "severity": "green",
                "reason": "Relevant experience.",
                "quote": "Built a FastAPI service",
                "source_id": "bullet-0",
            }
        ],
        "gaps": ["No Kubernetes experience found"],
        "draft_sentences": [
            {
                "text": "I built a FastAPI service.",
                "quote": "Built a FastAPI service",
                "source_id": "bullet-0",
            }
        ],
    }
)


def test_analyze_parses_well_formed_structured_response():
    fake_client = _FakeClient(response=_FakeResponse([_TextBlock(VALID_CANDIDATE_JSON)]))
    provider = ClaudeProvider(client=fake_client)

    result = provider.analyze(
        "Backend Engineer JD", [("bullet-0", "Built a FastAPI service")], ""
    )

    assert result.match_band == "good"
    assert result.flags[0].label == "Backend"
    assert result.draft_sentences[0].source_id == "bullet-0"


def test_analyze_sends_structured_output_config():
    fake_client = _FakeClient(response=_FakeResponse([_TextBlock(VALID_CANDIDATE_JSON)]))
    provider = ClaudeProvider(client=fake_client)

    provider.analyze("JD", [("bullet-0", "text")], "")

    kwargs = fake_client.messages.last_kwargs
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "match_band" in kwargs["output_config"]["format"]["schema"]["properties"]


def test_analyze_raises_llm_provider_error_on_connection_failure():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = ClaudeProvider(client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.analyze("JD", [("bullet-0", "text")], "")
