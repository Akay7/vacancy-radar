# Contract: `LLMProvider.draft_vacancy_metadata()` (extended)

This is the one interface both `ClaudeProvider` and `OllamaProvider` must keep implementing
identically (Constitution III) — the contract already established in
[[006-vacancy-upload]]'s `contracts/ingest-upload-routes.md`, extended here with two optional
parameters.

## Signature

```python
def draft_vacancy_metadata(
    self,
    document_text: str,
    image_bytes: bytes | None = None,
    image_media_type: str | None = None,
) -> DraftVacancyMetadata:
    ...
```

## Behavior contract (both providers)

1. **No image** (`image_bytes is None`): behavior is byte-for-byte unchanged from
   [[006-vacancy-upload]] — the existing text-only prompt/flow, unaffected by this feature.
2. **Image given, vision attempt succeeds**: returns a `DraftVacancyMetadata` derived from the
   model's own reading of the image — `date` still defaults to today's date if the model
   returns an empty string, exactly as the existing text path already does.
3. **Image given, vision attempt fails** (backend error, malformed/non-JSON response, no
   vision support): raises `LLMProviderError` directly. There is **no internal fallback** to a
   text-only attempt — `document_text` is always `""` for images (local OCR is removed, FR-008)
   so a text-only retry would have nothing to work from.
4. **Never distinguishes "the model doesn't support images" as a separate exception type** —
   every vision-path failure surfaces the same way (`LLMProviderError`), and it's `api.py`,
   which already knows the upload was an image, that renders the specific FR-002 message —
   not the provider.

## HTTP-level contract: `POST /ui/ingest/draft` (unchanged shape, changed messaging)

The request/response *shape* of this route, as documented in
[[006-vacancy-upload]]'s `contracts/ingest-upload-routes.md`, does **not** change: multipart
file upload in, `_ingest_draft.html` partial out (draft fields pre-filled, or a friendly
`message` when drafting didn't produce anything). What changes for image uploads specifically:

- `ingest_draft()` no longer calls `documents.extract_text()` for image uploads at all (it
  always returns `""` for images now — see research.md #2) — it passes `image_bytes`/
  `image_media_type` straight through instead.
- The route no longer skips the LLM call when there's no text to work from, *as long as an
  image is present* — the skip condition becomes `if not document_text and image_bytes is
  None`, so an image upload always attempts drafting.
- On `LLMProviderError` (or `ValidationError`/`json.JSONDecodeError`) from an image upload, the
  route renders a **specific** message distinct from the generic one used for non-image
  failures — e.g. "Your configured LLM backend couldn't read this image directly — image-based
  drafting isn't available with the current setup. Fill in every field manually below, or
  switch to a vision-capable model." This is what satisfies FR-002; the provider layer itself
  raises only the one generic `LLMProviderError`.

## Non-goals (explicitly out of scope, per spec.md Assumptions)

- No capability-detection call (e.g. Models API, model-name string matching) to decide
  up front whether a configured model supports vision.
- No OCR-based fallback of any kind — local OCR (`pytesseract`) is removed from the project
  entirely, not merely bypassed for this feature.
- No change to PDF/DOCX/plain-text handling — `image_bytes`/`image_media_type` are always
  `None` for those, and their `document_text` extraction (`pypdf`/`python-docx`) is untouched.
- No new HTTP routes or request/response fields on `POST /ui/ingest/draft`.
