"""Unified LLM provider settings, read once from the environment.

`LLM_PROVIDER` and `LLM_MODEL` together select the chat model backend — e.g.
`LLM_PROVIDER=anthropic LLM_MODEL=claude-opus-5` or `LLM_PROVIDER=ollama LLM_MODEL=qwen3:8b` —
the exact `model_provider`/`model` pair LangChain's own `init_chat_model()` already knows how to
resolve to a concrete `BaseChatModel`. There is no default and no fallback: this project doesn't
special-case Claude or Ollama anywhere, so it doesn't get to assume one of them either — every
deployment sets both explicitly. Any provider LangChain supports works here, as long as its
`langchain-<provider>` package is installed (`init_chat_model()` raises a clear
`pip install langchain-<provider>` error otherwise); adding a new backend is a config change,
not a code change.

`LLM_BASE_URL` is a vendor-neutral override for self-hosted/local backends — e.g.
`langchain-ollama`, unlike most providers, which read their own credential from a standard env
var the way `ChatAnthropic` reads `ANTHROPIC_API_KEY`, has no such env var for its base URL, so
it must be passed in explicitly. Left unset, each provider falls back to its own default (Ollama
to `http://localhost:11434`); which providers actually accept a `base_url` override is
`get_llm_provider()`'s concern, not this module's.

This class only reads settings — deciding what to do with them (building the actual chat model)
is `get_llm_provider()`'s job (api.py), not this module's.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
