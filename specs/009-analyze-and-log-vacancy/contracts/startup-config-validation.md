# Contract: Startup LLM Configuration Validation

## `validate_llm_provider_config() -> None`

Raises `RuntimeError` with a specific, actionable message if the configured provider is missing
required configuration. Returns normally (no side effects) otherwise.

| `LLM_PROVIDER` | Required | Missing-config message (example) |
|---|---|---|
| `claude` (default/unset) | `ANTHROPIC_API_KEY` non-empty | `"ANTHROPIC_API_KEY is not set. It's required when LLM_PROVIDER=claude (the default). Set it in your environment or .env, or set LLM_PROVIDER=ollama for a fully local/offline setup."` |
| `ollama` | *(none)* | N/A — `OLLAMA_HOST`/`OLLAMA_MODEL` both have working defaults; no secret is required |

## Wiring: FastAPI `lifespan`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_llm_provider_config()
    yield

app = FastAPI(title="Vacancy Radar", version="0.1.0", lifespan=lifespan)
```

- Runs once, before the app starts accepting any requests — when run via `vacancy-radar serve`
  (or a direct `uvicorn vacancy_radar.api:app` invocation), a `RuntimeError` here causes the
  server process to fail to start (non-zero exit, message printed) rather than starting and
  failing on first request.
- Does **not** run for the existing test suite's `client = TestClient(app)` module-level usage
  (FastAPI/Starlette only triggers `lifespan` for `with TestClient(app) as client:`), so no
  existing test needs a fake `ANTHROPIC_API_KEY` — confirmed by inspecting every current test
  file's `TestClient` usage (research.md #5).
- The one new test for this behavior explicitly uses the context-manager form to opt into
  triggering it.

## Non-goals

- No connectivity/reachability check (e.g. pinging `OLLAMA_HOST`, making a real Anthropic API
  call) — this validates that required *configuration values* are present, not that the backend
  is currently reachable. A backend that's configured but temporarily down still fails the
  existing way (`LLMProviderError` → friendly per-request message), unchanged.
- No new environment variables — this checks the existing `ANTHROPIC_API_KEY`/`LLM_PROVIDER`
  variables `get_llm_provider()` already reads.
