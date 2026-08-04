import json
from datetime import date

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
        self.call_count = 0

    def create(self, **kwargs):
        self.call_count += 1
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


VALID_DRAFT_JSON = json.dumps(
    {"company": "Acme Corp", "position": "Backend Engineer", "date": "2026-01-15"}
)


def test_draft_vacancy_metadata_parses_well_formed_response():
    fake_client = _FakeClient(response=_FakeResponse([_TextBlock(VALID_DRAFT_JSON)]))
    provider = ClaudeProvider(client=fake_client)

    result = provider.draft_vacancy_metadata("Acme Corp is hiring a Backend Engineer...")

    assert result.company == "Acme Corp"
    assert result.position == "Backend Engineer"
    assert result.date.isoformat() == "2026-01-15"


def test_draft_vacancy_metadata_defaults_date_to_today_when_blank():
    blank_date_json = json.dumps(
        {"company": "Acme Corp", "position": "Backend Engineer", "date": ""}
    )
    fake_client = _FakeClient(response=_FakeResponse([_TextBlock(blank_date_json)]))
    provider = ClaudeProvider(client=fake_client)

    result = provider.draft_vacancy_metadata("some document text with no date mentioned")

    assert result.date == date.today()


def test_draft_vacancy_metadata_raises_llm_provider_error_on_connection_failure():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = ClaudeProvider(client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata("some document text")


# --- Vision-based drafting for image uploads (specs/007-vision-drafting) -----------------


def test_draft_vacancy_metadata_sends_vision_content_block_for_image():
    fake_client = _FakeClient(response=_FakeResponse([_TextBlock(VALID_DRAFT_JSON)]))
    provider = ClaudeProvider(client=fake_client)

    result = provider.draft_vacancy_metadata(
        "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
    )

    kwargs = fake_client.messages.last_kwargs
    content = kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    image_block = next(block for block in content if block["type"] == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    text_block = next(block for block in content if block["type"] == "text")
    assert isinstance(text_block["text"], str) and text_block["text"]
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert result.company == "Acme Corp"


def test_draft_vacancy_metadata_raises_llm_provider_error_on_vision_failure_no_fallback():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = ClaudeProvider(client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata(
            "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
        )

    # exactly one attempt was made — no second/fallback request
    assert fake_client.messages.call_count == 1


# --- Vision-based text extraction for image analysis (specs/009-analyze-and-log-vacancy) --


def test_extract_document_text_sends_vision_content_block_and_returns_plain_text():
    fake_client = _FakeClient(
        response=_FakeResponse([_TextBlock("Backend Engineer role at Acme Corp...")])
    )
    provider = ClaudeProvider(client=fake_client)

    result = provider.extract_document_text(b"fake-png-bytes", "image/png")

    kwargs = fake_client.messages.last_kwargs
    content = kwargs["messages"][0]["content"]
    image_block = next(block for block in content if block["type"] == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    text_block = next(block for block in content if block["type"] == "text")
    assert isinstance(text_block["text"], str) and text_block["text"]
    assert "output_config" not in kwargs  # plain text response, not schema-constrained
    assert result == "Backend Engineer role at Acme Corp..."


def test_extract_document_text_raises_llm_provider_error_on_failure():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = ClaudeProvider(client=fake_client)

    with pytest.raises(LLMProviderError):
        provider.extract_document_text(b"fake-png-bytes", "image/png")
