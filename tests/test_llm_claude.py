import base64
import json
from datetime import date

import anthropic
import httpx
import pytest
from anthropic.types import Message, TextBlock, Usage

from vacancy_radar.llm.base import LLMProviderError
from vacancy_radar.llm.claude import ClaudeProvider


def _fake_message(text: str) -> Message:
    """A real anthropic.types.Message — ChatAnthropic's response-formatting code expects a
    genuine pydantic object (.model_dump()), not a bare stand-in, so fakes are built from the
    real SDK type rather than a hand-rolled shape."""
    return Message(
        id="msg_test",
        content=[TextBlock(type="text", text=text)],
        model="claude-opus-5",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )


class _FakeMessages:
    def __init__(self, response: Message | None = None, error: Exception | None = None) -> None:
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
    def __init__(self, response: Message | None = None, error: Exception | None = None) -> None:
        self.messages = _FakeMessages(response=response, error=error)


def _provider_with_fake_client(fake_client: _FakeClient) -> ClaudeProvider:
    """ClaudeProvider constructs a real ChatAnthropic; its `_client` attribute (a real
    anthropic.Anthropic instance) is swapped for the fake post-construction — there's no
    client= constructor injection point on ChatAnthropic itself (verified)."""
    provider = ClaudeProvider()
    provider._chat_model._client = fake_client
    return provider


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
    fake_client = _FakeClient(response=_fake_message(VALID_CANDIDATE_JSON))
    provider = _provider_with_fake_client(fake_client)

    result = provider.analyze(
        "Backend Engineer JD", [("bullet-0", "Built a FastAPI service")], ""
    )

    assert result.match_band == "good"
    assert result.flags[0].label == "Backend"
    assert result.draft_sentences[0].source_id == "bullet-0"


def test_analyze_sends_json_schema_structured_output():
    fake_client = _FakeClient(response=_fake_message(VALID_CANDIDATE_JSON))
    provider = _provider_with_fake_client(fake_client)

    provider.analyze("JD", [("bullet-0", "text")], "")

    kwargs = fake_client.messages.last_kwargs
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "match_band" in kwargs["output_config"]["format"]["schema"]["properties"]


def test_analyze_raises_llm_provider_error_on_connection_failure():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.analyze("JD", [("bullet-0", "text")], "")


VALID_DRAFT_JSON = json.dumps(
    {"company": "Acme Corp", "position": "Backend Engineer", "date": "2026-01-15"}
)


def test_draft_vacancy_metadata_parses_well_formed_response():
    fake_client = _FakeClient(response=_fake_message(VALID_DRAFT_JSON))
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata("Acme Corp is hiring a Backend Engineer...")

    assert result.company == "Acme Corp"
    assert result.position == "Backend Engineer"
    assert result.date.isoformat() == "2026-01-15"


def test_draft_vacancy_metadata_defaults_date_to_today_when_blank():
    blank_date_json = json.dumps(
        {"company": "Acme Corp", "position": "Backend Engineer", "date": ""}
    )
    fake_client = _FakeClient(response=_fake_message(blank_date_json))
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata("some document text with no date mentioned")

    assert result.date == date.today()


def test_draft_vacancy_metadata_raises_llm_provider_error_on_connection_failure():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata("some document text")


# --- Vision-based drafting for image uploads (specs/007-vision-drafting) -----------------


def test_draft_vacancy_metadata_sends_vision_content_block_for_image():
    fake_client = _FakeClient(response=_fake_message(VALID_DRAFT_JSON))
    provider = _provider_with_fake_client(fake_client)

    result = provider.draft_vacancy_metadata(
        "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
    )

    kwargs = fake_client.messages.last_kwargs
    content = kwargs["messages"][0]["content"]
    assert isinstance(content, list)
    image_block = next(block for block in content if block["type"] == "image")
    assert image_block["source"]["type"] == "base64"
    assert image_block["source"]["media_type"] == "image/png"
    assert image_block["source"]["data"] == base64.standard_b64encode(b"fake-png-bytes").decode()
    text_block = next(block for block in content if block["type"] == "text")
    assert isinstance(text_block["text"], str) and text_block["text"]
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    assert result.company == "Acme Corp"


def test_draft_vacancy_metadata_raises_llm_provider_error_on_vision_failure_no_fallback():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    fake_client = _FakeClient(error=error)
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.draft_vacancy_metadata(
            "", image_bytes=b"fake-png-bytes", image_media_type="image/png"
        )

    # exactly one attempt was made — no second/fallback request
    assert fake_client.messages.call_count == 1


# --- Vision-based text extraction for image analysis (specs/009-analyze-and-log-vacancy) --


def test_extract_document_text_sends_vision_content_block_and_returns_plain_text():
    fake_client = _FakeClient(response=_fake_message("Backend Engineer role at Acme Corp..."))
    provider = _provider_with_fake_client(fake_client)

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
    provider = _provider_with_fake_client(fake_client)

    with pytest.raises(LLMProviderError):
        provider.extract_document_text(b"fake-png-bytes", "image/png")
