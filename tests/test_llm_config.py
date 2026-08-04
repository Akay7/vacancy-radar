import pytest
from pydantic import ValidationError

from vacancy_radar.llm.config import LLMConfig


def test_defaults_to_claude_with_no_api_key(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = LLMConfig()

    assert config.llm_provider == "claude"
    assert config.anthropic_api_key is None


def test_reads_anthropic_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

    config = LLMConfig()

    assert config.anthropic_api_key == "sk-test-123"


def test_ollama_defaults_when_no_overrides_given(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    config = LLMConfig()

    assert config.llm_provider == "ollama"
    assert config.ollama_model == "qwen3:8b"
    assert config.ollama_host == "http://localhost:11434"


def test_reads_ollama_overrides_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:70b")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")

    config = LLMConfig()

    assert config.ollama_model == "llama3:70b"
    assert config.ollama_host == "http://ollama:11434"


def test_invalid_llm_provider_value_raises(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")  # not a supported provider

    with pytest.raises(ValidationError):
        LLMConfig()
