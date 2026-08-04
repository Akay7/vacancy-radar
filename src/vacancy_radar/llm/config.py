"""Unified LLM provider configuration, read once from the environment.

`ANTHROPIC_API_KEY`/`OLLAMA_MODEL`/`OLLAMA_HOST` were previously each read directly via
`os.environ.get(...)` in `get_llm_provider()`. `LLMConfig` is the single place that reads and
types them.

No `LLM_PROVIDER` selector: which provider runs is inferred from whether `anthropic_api_key` is
set — set it to use Claude, leave it unset for a fully local/offline setup via Ollama (whose
`ollama_model`/`ollama_host` defaults always work, so there is no "missing config" state to fail
on for that path).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: str | None = None
    ollama_model: str = "qwen3:8b"
    ollama_host: str = "http://localhost:11434"
