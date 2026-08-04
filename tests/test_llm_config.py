from vacancy_radar.llm.config import LLMConfig


def test_no_llm_provider_or_model_leaves_them_unset(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    config = LLMConfig()

    assert config.llm_provider is None
    assert config.llm_model is None


def test_reads_llm_provider_and_model_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5")

    config = LLMConfig()

    assert config.llm_provider == "anthropic"
    assert config.llm_model == "claude-opus-5"


def test_llm_base_url_unset_by_default(monkeypatch) -> None:
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    config = LLMConfig()

    assert config.llm_base_url is None


def test_reads_llm_base_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://ollama:11434")

    config = LLMConfig()

    assert config.llm_base_url == "http://ollama:11434"
