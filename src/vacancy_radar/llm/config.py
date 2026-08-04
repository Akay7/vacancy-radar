"""Unified LLM provider configuration, read once from the environment.

Previously `LLM_PROVIDER`/`ANTHROPIC_API_KEY`/`OLLAMA_MODEL`/`OLLAMA_HOST` were each read
directly via `os.environ.get(...)`, duplicated across `get_llm_provider()` (provider
construction) and `validate_llm_provider_config()` (startup check) in `api.py`. `LLMConfig`
is the single place that reads and types them; both call sites construct one and use its
fields instead of touching `os.environ` themselves.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    llm_provider: Literal["claude", "ollama"] = "claude"
    anthropic_api_key: str | None = None
    ollama_model: str = "qwen3:8b"
    ollama_host: str = "http://localhost:11434"
