import json
from datetime import date

import httpx
import ollama
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


class _FakeOllamaClient:
    """Fakes ollama._client.Client.chat() — ChatOllama's non-streaming _generate() path
    actually always drives the client in streaming mode internally (verified), so .chat()
    must return an iterator of ollama.ChatResponse chunks, not a single response."""

    def __init__(self, contents: list[str] | None = None, error: Exception | None = None) -> None:
        self._contents = list(contents) if contents is not None else None
        self._error = error
        self.calls: list[dict] = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        content = self._contents.pop(0)
        yield ollama.ChatResponse(
            model="qwen3:8b",
            created_at="2026-01-01T00:00:00Z",
            done=True,
            done_reason="stop",
            message=ollama.Message(role="assistant", content=content),
        )


def _provider_with_fake_client(fake_client: _FakeOllamaClient) -> OllamaProvider:
    provider = OllamaProvider()
    provider._chat_model._client = fake_client
    return provider


def test_analyze_parses_valid_json_on_first_try():
    fake_client = _FakeOllamaClient(contents=[json.dumps(VALID_CANDIDATE)])
    provider = _provider_with_fake_client(fake_client)

    result = provider.analyze("JD", [("bullet-0", "Built a FastAPI service")], "")

    assert result.match_band == "good"
    assert len(fake_client.calls) == 1


def test_analyze_sends_json_schema_structured_output():
    fake_client = _FakeOllamaClient(contents=[json.dumps(VALID_CANDIDATE)])
    provider = _provider_with_fake_client(fake_client)

    provider.analyze("JD", [("bullet-0", "text")], "")

    assert "match_band" in fake_client.calls[0]["format"]["properties"]


def test_analyze_retries_once_on_invalid_json():
    fake_client = _FakeOllamaClient(contents=["not json at all", json.dumps(VALID_CANDIDATE)])
    provider = _provider_with_fake_client(fake_client)

    result = provider.analyze("JD", [("bullet-0", "text")], "")

    assert result.match_band == "good"
    assert len(fake_client.calls) == 2


def test_analyze_raises_after_second_invalid_json():
    fake_client = _FakeOllamaClient(contents=["still not json", "still not json either"])
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.analyze("JD", [("bullet-0", "text")], "")

    assert len(fake_client.calls) == 2  # one retry, then give up


def test_analyze_raises_llm_provider_error_on_connection_failure():
    fake_client = _FakeOllamaClient(error=httpx.ConnectError("connection refused"))
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.analyze("JD", [("bullet-0", "text")], "")


VALID_DRAFT = {"company": "Acme Corp", "position": "Backend Engineer", "date": "2026-01-15"}
VALID_DRAFT_JSON = json.dumps(VALID_DRAFT)
BLANK_DATE_DRAFT_JSON = json.dumps(
    {"company": "Acme Corp", "position": "Backend Engineer", "date": ""}
)


def test_draft_vacancy_metadata_parses_valid_json_on_first_try():
    fake_client = _FakeOllamaClient(contents=[VALID_DRAFT_JSON])
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata("Acme Corp is hiring a Backend Engineer...")

    assert result.company == "Acme Corp"
    assert result.date.isoformat() == "2026-01-15"


def test_draft_vacancy_metadata_defaults_date_to_today_when_blank():
    fake_client = _FakeOllamaClient(contents=[BLANK_DATE_DRAFT_JSON])
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata("some document text with no date mentioned")

    assert result.date == date.today()


def test_draft_vacancy_metadata_retries_once_on_invalid_json():
    fake_client = _FakeOllamaClient(contents=["not json at all", VALID_DRAFT_JSON])
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata("some document text")

    assert result.company == "Acme Corp"
    assert len(fake_client.calls) == 2


def test_draft_vacancy_metadata_raises_llm_provider_error_on_connection_failure():
    fake_client = _FakeOllamaClient(error=httpx.ConnectError("connection refused"))
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata("some document text")


# --- Vision-based drafting for image uploads (specs/007-vision-drafting) -----------------


def test_draft_vacancy_metadata_sends_images_field_for_image():
    fake_client = _FakeOllamaClient(contents=[VALID_DRAFT_JSON])
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata(
        "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
    )

    assert len(fake_client.calls) == 1
    images = fake_client.calls[0]["messages"][0]["images"]
    assert len(images) == 1 and images[0]  # non-empty base64 string
    assert result.company == "Acme Corp"


def test_draft_vacancy_metadata_raises_llm_provider_error_on_vision_failure_no_fallback():
    fake_client = _FakeOllamaClient(error=httpx.ConnectError("connection refused"))
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata(
            "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
        )

    # exactly one attempt was made — no fallback retry
    assert len(fake_client.calls) == 1


# --- Vision-based text extraction for image analysis (specs/009-analyze-and-log-vacancy) --


def test_extract_document_text_sends_images_field_and_returns_plain_text():
    fake_client = _FakeOllamaClient(contents=["Backend Engineer role at Acme Corp..."])
    provider = _provider_with_fake_client(fake_client)

    result = provider.extract_document_text(b"fake-png-bytes", "image/png")

    assert len(fake_client.calls) == 1
    images = fake_client.calls[0]["messages"][0]["images"]
    assert len(images) == 1 and images[0]
    assert fake_client.calls[0].get("format") is None  # plain text, not JSON-constrained
    assert result == "Backend Engineer role at Acme Corp..."


def test_extract_document_text_raises_llm_provider_error_on_connection_failure():
    fake_client = _FakeOllamaClient(error=httpx.ConnectError("connection refused"))
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.extract_document_text(b"fake-png-bytes", "image/png")
