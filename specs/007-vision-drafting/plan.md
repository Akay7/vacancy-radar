# Implementation Plan: Vision-Based Image Drafting

**Branch**: `007-vision-drafting` | **Date**: 2026-08-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/007-vision-drafting/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

When a maintainer uploads an image (photo/screenshot) through the existing upload UI
([[006-vacancy-upload]]), `LLMProvider.draft_vacancy_metadata()` now derives
company/position/date entirely from the LLM's own reading of the image (a vision content
block), replacing the previous `pytesseract` OCR step for images. Local OCR is removed from
the project entirely — there is no OCR-based intermediate text for images to fall back to. If
the configured backend can't interpret the image, or the vision attempt fails, the maintainer
sees a specific, plain-language message explaining that image-based drafting isn't available
with their current backend, and falls back to filling in every field manually — the same floor
[[006-vacancy-upload]] already guarantees for any failed draft. PDF/DOCX/plain-text uploads are
completely unaffected (they never used OCR).

## Technical Context

**Language/Version**: Python 3.11 (unchanged)

**Primary Dependencies**: `anthropic` SDK (already a dependency — `messages.create` already
used for `output_config.format`; this feature adds an `image` content block to the same call,
no version bump required), `httpx` (already used by `OllamaProvider._chat()` — extended to
send Ollama's `images` field). **Removed**: `pytesseract`, `Pillow` — both were added in 006
solely for local OCR, which this feature removes entirely (FR-008); the `tesseract-ocr` system
package is also removed from the Dockerfile. No new dependencies are added.

**Storage**: N/A — no new persisted entities; `DraftVacancyMetadata` is unchanged.

**Testing**: `pytest`, following the existing `FakeAnthropicClient`/`httpx` mocking patterns
already established in `tests/test_llm_claude.py` / `tests/test_llm_ollama.py`.

**Target Platform**: Linux server / Docker (unchanged; Dockerfile gets simpler — one fewer
system package to install).

**Project Type**: Single project (existing structure, no new top-level directories).

**Performance Goals**: N/A explicit — qualitative accuracy improvement only (spec SC-001).

**Constraints**: Image bytes MUST NOT be sent anywhere but the maintainer's own configured
`LLMProvider` backend (FR-007) — same private-by-default boundary as the existing OCR text
path did. A backend without vision support MUST still leave the maintainer able to complete
the upload via manual entry (FR-003) — it does not need to remain "just as capable" as before,
only non-blocking, since the feature explicitly favors an honest failure signal over a silent
intermediate fallback (Constitution III's shared-interface requirement still holds either way).

**Scale/Scope**: One image per upload request, same as the existing `POST /ui/ingest/draft`
flow — no change in request volume or concurrency.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Local-First & Private by Default** — PASS. The image is read from the same staged
  upload file already written to local disk by `POST /ui/ingest/draft`; it is sent only to
  whichever `LLMProvider` backend the maintainer already configured (Claude API or their own
  Ollama instance), never to a third-party vision/OCR service.
- **II. Grounded Generation (NON-NEGOTIABLE)** — N/A. `draft_vacancy_metadata()` is not part of
  `/analyze`'s citation-grounded generation path (established in 006); its output is always
  maintainer-reviewed before being saved, never auto-trusted regardless of source (FR-006).
- **III. Pluggable, Provider-Agnostic LLM** — PASS. `LLMProvider.draft_vacancy_metadata()`
  keeps one shared method signature and one call site (`api.py`'s `ingest_draft`); both
  `ClaudeProvider` and `OllamaProvider` implement it identically — attempt vision, raise
  `LLMProviderError` on any failure — and `api.py` (not the provider) is what decides how to
  phrase the resulting message. Calling code never special-cases either provider, matching how
  `analyze()` already differs internally (structured schema vs. JSON-mode-plus-retry) behind
  one shared method today.
- **IV. Simplicity & Right-Sized Infra (YAGNI)** — PASS, and improved: this feature *removes*
  two dependencies (`pytesseract`, `Pillow`) and a system package (`tesseract-ocr`) rather than
  adding any. Reuses the existing `DRAFT_METADATA_JSON_SCHEMA` as the structured-output
  contract for the vision path.
- **V. Test & Lint Gates** — PASS (planned). New tests required: Claude vision success, Claude
  vision failure → specific error surfaced, Ollama vision attempt via the `images` field,
  Ollama vision failure → specific error surfaced, plus removal of now-obsolete OCR tests in
  `tests/test_documents.py`. `ruff`/`pytest` must stay green.
- **VI. Regenerable Derived State** — PASS. No ingestion/Chroma schema changes; image source
  files in existing vacancy folders simply embed as empty-text chunks going forward (see
  research.md), which the existing `chunk_vacancy_folder`/upsert logic already handles without
  modification — nothing to regenerate or re-key.

No violations — Complexity Tracking is not needed for this feature.

## Project Structure

### Documentation (this feature)

```text
specs/007-vision-drafting/
├── plan.md                          # This file (/speckit-plan command output)
├── research.md                      # Phase 0 output (/speckit-plan command)
├── data-model.md                    # Phase 1 output (/speckit-plan command)
├── quickstart.md                    # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── llm-provider-vision.md       # Phase 1 output (/speckit-plan command)
└── tasks.md                         # Phase 2 output (/speckit-tasks command - NOT created here)
```

### Source Code (repository root)

```text
src/vacancy_radar/
├── documents.py           # - _extract_image() / pytesseract / PIL.Image (removed)
│                          # + IMAGE_MEDIA_TYPES mapping (extension → MIME type, still needed
│                          #   for the vision request); extract_text() returns "" for images
├── llm/
│   ├── base.py             # LLMProvider.draft_vacancy_metadata() gains optional
│   │                        # image_bytes / image_media_type params
│   ├── prompts.py          # + build_draft_metadata_vision_prompt() (image-only, no OCR hint)
│   ├── claude.py           # vision content block + output_config.format; raises
│   │                        # LLMProviderError on any failure (no text-fallback attempt)
│   └── ollama.py           # images field on /api/chat; same raise-on-failure behavior
└── api.py                  # ingest_draft(): reads image bytes for image uploads, never calls
                             # documents.extract_text() for them; shows a specific message on
                             # LLMProviderError when the upload was an image

pyproject.toml              # - pytesseract, Pillow (removed from [project].dependencies)
Dockerfile                  # - tesseract-ocr apt-get install (removed)

tests/
├── test_documents.py        # - OCR-specific tests (removed); + IMAGE_MEDIA_TYPES coverage
├── test_llm_claude.py       # + vision-success / vision-failure-raises cases
├── test_llm_ollama.py       # + images-field-sent / vision-failure-raises cases
├── test_api.py              # FakeLLMProvider stub signature updated
└── test_ui.py               # FakeLLMProvider stub signature updated; + image-specific-message
                              # test
```

**Structure Decision**: Existing single-project layout (`src/vacancy_radar/`, `tests/`),
unchanged from 005/006 — this feature only extends/prunes files already established by those
features (`llm/`, `documents.py`, `api.py`, `pyproject.toml`, `Dockerfile`). No new modules,
packages, or directories. `ingest.py` needs **no changes** — its existing `NON_TEXT_SOURCE_EXTENSIONS`
routing already sends image files through `documents.extract_text()`, which now simply returns
`""` for them instead of doing OCR (see research.md).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations — this section is intentionally empty.
