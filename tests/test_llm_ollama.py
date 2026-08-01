import json

import httpx
import pytest

from vacancy_radar.llm.base import LLMProviderError
from vacancy_radar.llm.ollama import OllamaProvider

VALID_CANDIDATE = {
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
    "gaps": [],
    "draft_sentences": [],
}


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"message": {"content": self._content}}


def test_analyze_parses_valid_json_on_first_try(monkeypatch):
    calls = []
    valid_response_body = json.dumps(VALID_CANDIDATE)

    def fake_post(url, json, timeout):
        calls.append(json)
        return _FakeResponse(valid_response_body)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    result = provider.analyze("JD", [("bullet-0", "Built a FastAPI service")], "")

    assert result.match_band == "good"
    assert len(calls) == 1


def test_analyze_retries_once_on_invalid_json(monkeypatch):
    responses = [_FakeResponse("not json at all"), _FakeResponse(json.dumps(VALID_CANDIDATE))]

    def fake_post(url, json, timeout):
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    result = provider.analyze("JD", [("bullet-0", "text")], "")

    assert result.match_band == "good"
    assert responses == []  # both queued responses were consumed


def test_analyze_raises_after_second_invalid_json(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResponse("still not json")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    with pytest.raises(LLMProviderError):
        provider.analyze("JD", [("bullet-0", "text")], "")


def test_analyze_raises_llm_provider_error_on_connection_failure(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    with pytest.raises(LLMProviderError):
        provider.analyze("JD", [("bullet-0", "text")], "")
