# Implementation Plan: Analyze and Log a Vacancy in One Pass

**Branch**: `009-analyze-and-log-vacancy` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/009-analyze-and-log-vacancy/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Let the Analyze screen (`/`) accept an uploaded document (image/PDF/DOCX/text — the same set
`/ingest` already accepts) as an alternative to pasting text. For PDF/DOCX/text, the already-local
`documents.extract_text()` output feeds the existing grounded-analysis pipeline unchanged. For
images, a new small `LLMProvider.extract_document_text()` vision call produces a plain-text
transcription used only to drive the existing bullet/similar-vacancy retrieval (still no local
OCR — the LLM reads the image directly, same category of thing as the existing vision drafting,
not a reintroduction of what specs/007-vision-drafting removed). Either way, `draft_vacancy_metadata()`
(unchanged) drafts company/position/date from the same upload, and the rendered result shows the
match report and the drafted fields together, reusing the existing `_ingest_draft.html`
form/`POST /ingest/confirm` route completely unchanged for the actual save — this feature adds a
second place to reach "logged vacancy," not a second way of doing it. Pasting text keeps
producing exactly today's report-only result. Separately (per user direction added mid-spec),
the app now validates at startup that the configured LLM provider has its required configuration
(e.g. `ANTHROPIC_API_KEY` for Claude) — refusing to start with a specific message instead of
starting normally and failing later with an opaque, uncaught error on the first real request
(confirmed as a real gap: `anthropic.Anthropic()` doesn't validate the key at construction, and
the resulting `TypeError` on first use isn't one of the exception types the existing
`LLMProviderError` wrapping already catches).

## Technical Context

**Language/Version**: Python 3.11 (unchanged).

**Primary Dependencies**: None new. Reuses `anthropic`/`httpx` (already present) for the new
vision text-extraction call, and FastAPI's `lifespan` context-manager parameter (already part of
the installed `fastapi` package) for startup config validation.

**Storage**: N/A — no new persisted state; saving still goes through the unchanged
`POST /ingest/confirm` route and `ingest_lib.ingest_vacancies()`.

**Testing**: `pytest` + `TestClient`, same fake-provider pattern as every prior feature. The
startup-validation test is the first in this codebase to use `with TestClient(app) as client:`
(a context manager) specifically because FastAPI only runs `lifespan` for that form — the
existing suite's module-level `client = TestClient(app)` calls never trigger it, so no existing
test needs a fake `ANTHROPIC_API_KEY` to keep passing.

**Target Platform**: Same as today — single `app` service, no new container/port.

**Project Type**: Web application — single FastAPI project (unchanged).

**Performance Goals**: An image upload on the Analyze screen now costs two LLM calls instead of
one (text extraction, then the existing grounded analyze call, plus drafting) — acceptable per
research.md #3, since this is a low-frequency, interactive, single-user action, not a hot path.

**Constraints**: `POST /api/analyze` (the JSON contract) is deliberately **not** extended with
upload support (research.md #1) — only the HTML `POST /analyze` route gains it. Saving a vacancy
from this screen must be byte-for-byte the same operation as today's `POST /ingest/confirm`
(FR-008) — no parallel save path is introduced.

**Scale/Scope**: One new `LLMProvider` method (implemented by both providers), one shared
upload-staging helper extracted from existing code, one route extended, one template gains an
optional included block, one startup-time config check — no new pages, no new persisted entities.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | No change — all LLM calls still go through the user's own configured backend; nothing new leaves the machine beyond what already does. | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | The image-upload path still produces its match report via the exact same `run_analysis()` → `grounding.enforce()` pipeline as pasted text — citations are still required on every claim; no separate, weaker grounding path is introduced for images. | PASS |
| III. Pluggable, Provider-Agnostic LLM | `extract_document_text()` is added to the `LLMProvider` ABC and implemented identically by `ClaudeProvider`/`OllamaProvider`; `api.py` calls it through the interface only, exactly like every existing method. | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | `POST /api/analyze` is deliberately left text-only (no stated consumer need for JSON-side uploads); saving is reused from `POST /ingest/confirm` unchanged rather than duplicated; the combined view is one `{% include %}`, not a new page or new save logic. | PASS |
| V. Test & Lint Gates | New provider method, new route branch, and the new startup check all get `pytest` coverage with the existing fake-provider pattern; `ruff` unaffected in scope. | PASS |
| VI. Regenerable Derived State | Unaffected — the same `ingest_lib.ingest_vacancies()` upsert-by-natural-key call embeds the saved vacancy, exactly as today. | PASS |

No violations to justify — Complexity Tracking section left empty.

*Re-checked post-Phase 1 (after research.md/data-model.md/contracts/quickstart.md were
written): unchanged — every new piece is either a same-shaped extension of an existing pattern
(vision method, provider-agnostic) or pure reuse (confirm route, draft partial).*

## Project Structure

### Documentation (this feature)

```text
specs/009-analyze-and-log-vacancy/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/vacancy_radar/
├── api.py                     # extended: _stage_and_read_upload() helper extracted from
│                               #   ingest_draft() (shared by it and the new analyze-with-upload
│                               #   branch); ui_analyze() (POST /analyze) gains an optional
│                               #   `file` param — when given, stages it, calls
│                               #   draft_vacancy_metadata() and (for images)
│                               #   extract_document_text(), then run_analysis() on the
│                               #   resulting text, and passes both results into _report.html's
│                               #   context; lifespan() context manager added, calling
│                               #   validate_llm_provider_config() before startup completes;
│                               #   app = FastAPI(..., lifespan=lifespan)
├── llm/base.py                 # extended: new abstract method
│                               #   extract_document_text(image_bytes, image_media_type) -> str
├── llm/claude.py                # extended: extract_document_text() — vision call, plain-text
│                               #   response (no JSON schema needed)
├── llm/ollama.py                # extended: extract_document_text() — _chat(prompt,
│                               #   images=[...]), plain-text response
├── llm/prompts.py                # extended: build_extract_document_text_vision_prompt() -> str
├── templates/
│   ├── index.html                # extended: form gains a file input (multipart) alongside the
│   │                             #   textarea; both submit to /analyze
│   └── _report.html               # extended: optional trailing
│                                 #   `{% include "_ingest_draft.html" %}` block, rendered only
│                                 #   when `upload_token` is present in context (absent/None for
│                                 #   the plain paste-text call, so today's output is byte-for-byte
│                                 #   unchanged when no file was uploaded)

tests/
├── test_llm_claude.py            # extended: extract_document_text() success/failure tests
├── test_llm_ollama.py            # extended: same, for OllamaProvider
├── test_ui.py                    # extended: POST /analyze with an uploaded file (PDF/text/image)
│                                 #   shows report + draft together and confirming saves via the
│                                 #   existing /ingest/confirm route; paste-only path asserted
│                                 #   unchanged (regression); a new `with TestClient(app) as
│                                 #   client:` test asserts startup fails with a specific message
│                                 #   when LLM_PROVIDER=claude and ANTHROPIC_API_KEY is unset
```

**Structure Decision**: Single project (unchanged) — everything stays inside the existing
`src/vacancy_radar` package and FastAPI app. No new template files: the combined view is
`_report.html` plus an existing partial it now conditionally includes, not a new page.

## Complexity Tracking

> No violations — this section is intentionally empty; see the Constitution Check table above.
