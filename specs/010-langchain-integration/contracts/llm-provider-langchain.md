# Contract: `LLMProvider` methods, migrated to `BaseChatModel`

The public shape calling code (`api.py`) depends on does not change — `analyze()`,
`draft_vacancy_metadata()`, `extract_document_text()` keep their existing signatures and return
types (`CandidateReport`, `DraftVacancyMetadata`, `str`). What changes is each method's
internals.

## Shared vision helper (new, replaces two separate request builders)

```python
def build_vision_message(prompt: str, image_bytes: bytes, image_media_type: str) -> HumanMessage:
    from langchain_core.messages import HumanMessage
    from langchain_core.messages.content import create_image_block

    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    return HumanMessage(content=[
        create_image_block(base64=image_b64, mime_type=image_media_type),
        {"type": "text", "text": prompt},
    ])
```

Verified (research.md #1) that both `ChatAnthropic` and `ChatOllama` translate this exact shape
into their respective wire formats correctly — one helper, used by both providers' vision paths
(`draft_vacancy_metadata()` with an image, `extract_document_text()`).

## `ClaudeProvider.analyze()` / `.draft_vacancy_metadata()` (text path)

```python
structured = self._chat_model.with_structured_output(CandidateReport, method="json_schema")
try:
    return structured.invoke(prompt)
except anthropic.APIError as exc:
    raise LLMProviderError(f"Claude API unreachable/misconfigured: {exc}") from exc
```

Standardizes on catching `anthropic.APIError` (the common base of `APIConnectionError`/
`AuthenticationError`/every other SDK error) uniformly across all four Claude call sites — today
`analyze()`/`_draft_from_text()` narrowly catch `(APIConnectionError, AuthenticationError)`
while `_draft_from_image()`/`extract_document_text()` already catch the broader `APIError`; this
migration makes that consistent rather than carrying the inconsistency forward.

Behavior contract (unchanged from today): a connection/auth failure raises `LLMProviderError`;
a successful call returns an already-validated `CandidateReport`/`DraftVacancyMetadata` — no
manual `json.loads`/`model_validate` step remains.

## `OllamaProvider.analyze()` / `.draft_vacancy_metadata()` (text path) — retry via `Runnable.with_retry()`

```python
structured = self._chat_model.with_structured_output(
    CandidateReport, method="json_schema"
).with_retry(retry_if_exception_type=(OutputParserException,), stop_after_attempt=2)

try:
    return structured.invoke(prompt)
except OutputParserException as exc:
    raise LLMProviderError("Ollama did not return valid JSON after one retry") from exc
```

Behavior contract: one retry on a malformed response (`stop_after_attempt=2`), same failure
mode covered as today — but the retry itself is LangChain's own `Runnable.with_retry()`
composition (research.md #2), not hand-rolled loop/instruction-append code. `LLMProviderError`
after both attempts fail.

## `extract_document_text()` — plain-text response, no structured output

```python
message = build_vision_message(prompt, image_bytes, image_media_type)
try:
    response = self._chat_model.invoke([message])
except anthropic.APIError as exc:
    raise LLMProviderError(f"Claude vision request failed: {exc}") from exc
return response.content  # plain string, no schema
```

Same shape for `OllamaProvider`, catching `httpx.HTTPError` (confirmed empirically, research.md
#3 — `ChatOllama` propagates `httpx.ConnectError`, a subclass, unchanged; today's
`except httpx.HTTPError` catch keeps working verbatim around the new `.invoke()` call).

## Non-goals

- No change to `LLMProviderError`'s definition or to any route's handling of it (`api.py`'s
  `except (LLMProviderError, ValidationError, json.JSONDecodeError)` blocks are unaffected).
- No change to prompt *content* — `build_analyze_prompt()`, `build_draft_metadata_prompt()`,
  `build_draft_metadata_vision_prompt()`, `build_extract_document_text_vision_prompt()` keep
  instructing the model in English the same way; only how their output is requested/parsed
  changes.
- No capability-detection call added — a vision-incapable model still fails at the same point
  (the `.invoke()` call) with the same specific error messaging `api.py` already produces for it
  (specs/007-vision-drafting, specs/009-analyze-and-log-vacancy).
