import json
from datetime import date

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


VALID_DRAFT = {"company": "Acme Corp", "position": "Backend Engineer", "date": "2026-01-15"}
VALID_DRAFT_JSON = json.dumps(VALID_DRAFT)
BLANK_DATE_DRAFT_JSON = json.dumps(
    {"company": "Acme Corp", "position": "Backend Engineer", "date": ""}
)


def test_draft_vacancy_metadata_parses_valid_json_on_first_try(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResponse(VALID_DRAFT_JSON)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    result = provider.draft_vacancy_metadata("Acme Corp is hiring a Backend Engineer...")

    assert result.company == "Acme Corp"
    assert result.date.isoformat() == "2026-01-15"


def test_draft_vacancy_metadata_defaults_date_to_today_when_blank(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResponse(BLANK_DATE_DRAFT_JSON)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    result = provider.draft_vacancy_metadata("some document text with no date mentioned")

    assert result.date == date.today()


def test_draft_vacancy_metadata_retries_once_on_invalid_json(monkeypatch):
    responses = [_FakeResponse("not json at all"), _FakeResponse(VALID_DRAFT_JSON)]

    def fake_post(url, json, timeout):
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    result = provider.draft_vacancy_metadata("some document text")

    assert result.company == "Acme Corp"
    assert responses == []


def test_draft_vacancy_metadata_raises_llm_provider_error_on_connection_failure(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata("some document text")


# --- Vision-based drafting for image uploads (specs/007-vision-drafting) -----------------


def test_draft_vacancy_metadata_sends_images_field_for_image(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(json)
        return _FakeResponse(VALID_DRAFT_JSON)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    result = provider.draft_vacancy_metadata(
        "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
    )

    assert len(calls) == 1
    images = calls[0]["messages"][0]["images"]
    assert len(images) == 1 and images[0]  # non-empty base64 string
    assert result.company == "Acme Corp"


def test_draft_vacancy_metadata_raises_llm_provider_error_on_vision_failure_no_fallback(
    monkeypatch,
):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(json)
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OllamaProvider()

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata(
            "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
        )

    # exactly one attempt was made — no fallback retry
    assert len(calls) == 1
