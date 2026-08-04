from vacancy_radar.llm.config import LLMConfig


def test_no_api_key_leaves_anthropic_api_key_unset(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    config = LLMConfig()

    assert config.anthropic_api_key is None


def test_reads_anthropic_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

    config = LLMConfig()

    assert config.anthropic_api_key == "sk-test-123"


def test_ollama_defaults_when_no_overrides_given(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    config = LLMConfig()

    assert config.ollama_model == "qwen3:8b"
    assert config.ollama_host == "http://localhost:11434"


def test_reads_ollama_overrides_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "llama3:70b")
    monkeypatch.setenv("OLLAMA_HOST", "http://ollama:11434")

    config = LLMConfig()

    assert config.ollama_model == "llama3:70b"
    assert config.ollama_host == "http://ollama:11434"
