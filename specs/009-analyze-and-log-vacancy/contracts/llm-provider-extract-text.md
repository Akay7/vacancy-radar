# Contract: `LLMProvider.extract_document_text()` (new)

A new method both `ClaudeProvider` and `OllamaProvider` must implement identically
(Constitution III) — added alongside the existing `analyze()` and `draft_vacancy_metadata()`.

## Signature

```python
def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str:
    ...
```

## Behavior contract (both providers)

1. **Purpose**: produce a plain-text transcription/summary of a job posting shown in an image —
   used exclusively to give the existing text-based retrieval (`retriever.query_bullets()` /
   `query_similar_vacancies()`) something to embed, since there is no other source of text for
   an image upload (research.md #2).
2. **Not JSON-structured**: unlike `draft_vacancy_metadata()`/`analyze()`, this returns a plain
   string, not a schema-validated object — there's no fixed shape to validate, just text.
3. **Always attempts vision directly** — no local OCR, no capability-detection call beforehand,
   consistent with `draft_vacancy_metadata()`'s existing image path.
4. **On failure** (backend error, no vision support, empty/unusable response): raises
   `LLMProviderError` directly. No fallback attempt exists — there is nothing to fall back to.
5. **Independent of `draft_vacancy_metadata()`**: a failure here does not affect drafting, and a
   drafting failure does not affect this — `api.py` calls both and handles each result
   independently (FR-007).

## Non-goals

- No change to `analyze()`'s signature — it still only accepts `jd_text` (research.md #2 covers
  why this method exists instead of an image-aware `analyze()`).
- No change to PDF/DOCX/plain-text handling — those already have real text via
  `documents.extract_text()` and never call this method.
- No persistence, no new response field on any existing route — this method's return value is
  used internally within one request and discarded afterward.
