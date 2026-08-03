# Quickstart: Validating Vision-Based Image Drafting

Manual, end-to-end validation — mirrors the pattern established in
[[006-vacancy-upload]]'s own `quickstart.md`, extended for this feature's two user stories.

## Prerequisites

- The app running (`docker compose up --build`, or bare `pip install -e .` + `uvicorn`).
- `VACANCY_DIR` pointed at a writable directory (`data/user/vacancies` by default).
- A real, imperfect photo or screenshot of a job posting (skewed, low light, or an unusual
  font OCR previously struggled with) — reusing the same kind of fixture that motivated this
  feature (specs/006-vacancy-upload's "Nimbus Cloud Systems" → "NimbusCloud systems" case).

## Scenario 1 — Vision-capable backend (User Story 1, P1)

1. Configure `LLM_PROVIDER=claude` with a real `ANTHROPIC_API_KEY` (or a local Ollama model
   known to support vision, e.g. `llava` or `qwen2.5vl`, via `LLM_PROVIDER=ollama` +
   `OLLAMA_MODEL=<vision-model>`).
2. Open `http://localhost:8000/ingest`, upload the imperfect photo.
3. **Expect**: drafted company/position/date reflect the image accurately — specifically,
   confirm any field that OCR previously got wrong (per the motivating case) is now correct.
4. Confirm every field is still editable before saving (FR-006) — change one field, save, and
   verify the saved `vacancy.yaml` reflects your edit, not the raw draft.

## Scenario 2 — Non-vision backend shows a clear, specific message (User Story 2, P2)

1. Configure `LLM_PROVIDER=ollama` with a text-only model (e.g. `qwen3:8b`, no vision support).
2. Upload the same photo.
3. **Expect**: a **specific** message explaining that this backend can't read images directly
   and drafting isn't available — not a generic "automatic drafting didn't work" message, and
   not a silently empty draft. Every field is still fillable and saves successfully.

## Scenario 3 — Vision attempt errors mid-request

1. With `LLM_PROVIDER=claude` configured, temporarily point `ANTHROPIC_API_KEY` at an invalid
   value (or disconnect network).
2. Upload the image.
3. **Expect**: the request doesn't hang or 500 — the same specific "couldn't read this image"
   message from Scenario 2 appears, and manual entry still saves successfully (FR-003).

## Scenario 4 — PDF/DOCX unaffected (SC-003 regression check)

1. Upload a PDF or DOCX posting (as in [[006-vacancy-upload]]'s own quickstart).
2. **Expect**: identical drafting behavior and accuracy to before this feature — no vision
   attempt, no behavior change.

## Automated coverage (for reference, not a substitute for the above)

- `tests/test_llm_claude.py`: vision-success path (fake Anthropic client returns a
  JSON-schema-shaped response for an image+text request); vision-failure path (fake client
  raises) results in `LLMProviderError`, with no second/fallback request attempted.
- `tests/test_llm_ollama.py`: `images` field is included in the request payload when an image
  is given; a failure on the image attempt results in `LLMProviderError`, with no fallback
  `_chat()` retry.
- `tests/test_ui.py`: `ingest_draft()` always attempts drafting for an image upload (never
  calls `documents.extract_text()` for images at all); on `LLMProviderError` for an image
  upload, the rendered message is the specific "this backend can't read images" wording, not
  the generic non-image failure message.
- `tests/test_documents.py`: `IMAGE_MEDIA_TYPES` covers every key in `IMAGE_EXTENSIONS`;
  `extract_text()` returns `""` for image paths (no OCR attempted).
