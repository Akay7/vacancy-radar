## Why

The MCP server exposes vacuum-radar's vault as structured tools (list, search, read, write),
but an LLM client using it must manually chain multiple tool calls to answer a natural-language
question. Users want to simply ask "how's my job search going?" or "what's the status of Acme Corp?"
and get a coherent answer — the "ingress via chat" capability.

## What Changes

- **New `chat` tool** on the MCP server. Accepts a text message and an optional
  session ID. The server maintains per-session conversation history and calls the
  configured LLM to produce a response. Context from the user's vault is gathered
  automatically (company list, search results) before the LLM call so the model
  always has current data.
- **New `chat_message` function in `core.py`** — the sole business logic for chat.
  Accepts a message and session data, queries the vault (company list via
  `list_vacancies`, resolves entities via `resolve`), and delegates to an
  OpenAI-compatible `chat.completions.create` API. Returns the assistant message.
  No external LLM calls live outside core.py (invariant 4).
- **Config wiring**: `OPENAI_BASE_URL` (env) resolves the chat API endpoint.
  `OPENAI_MODEL` (env, default `chatgpt-4o-mini`) selects the model.
  **BREAKING** if a previous MCP config key existed (none does yet).
- **New dependency**: `openai>=1.0.0` (the official client, thin wrapper around
  any OpenAI-compatible server).

## Capabilities

### New Capabilities
- `chat-ingress`: Natural-language chat capability exposed through the MCP
  server. The `chat` tool delegates to `core.chat_message` which maintains
  conversation sessions, gathers vault context automatically, and calls an
  OpenAI-compatible chat completions API.

### Modified Capabilities
- _(none)_ — no existing spec-level requirements are changing. The MCP server's
  invariant that "every tool delegates to core.py" is extended to the new tool.

## Impact

- **New files**: `src/vacancy_radar/chat.py` (core chat logic),
  `tests/test_chat.py` (unit tests), and a `test_chat` fixture helper in the
  existing test suite.
- **Modified files**: `src/vacancy_radar/mcp_server.py` (new `chat` tool),
  `src/vacancy_radar/mcp_server.py` (new `chat_sessions` resource),
  `src/vacancy_radar/core.py` (new `chat_message`, `ChatSession`,
  `EntityNotFoundError` already exists),
  `src/vacancy_radar/config.py` (new `resolve_openai_config`),
  `pyproject.toml` (new `openai` dependency).
- **No breaking changes to existing tools** — read/write tools are unaffected.
- **External dependency**: `openai>=1.0.0`. The client only makes HTTP calls
  at runtime (never at import/startup time).
