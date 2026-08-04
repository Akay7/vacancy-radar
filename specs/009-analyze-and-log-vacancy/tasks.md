---

description: "Task list for Analyze and Log a Vacancy in One Pass"
---

# Tasks: Analyze and Log a Vacancy in One Pass

**Input**: Design documents from `/specs/009-analyze-and-log-vacancy/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/llm-provider-extract-text.md, contracts/analyze-upload-routes.md,
contracts/startup-config-validation.md, quickstart.md

**Tests**: Included — this repo's established pattern (every prior feature: 003/005/006/007/008)
is tests-first, and Constitution V requires test coverage for new logic. The Foundational
phase's helper extraction is a refactor of *existing* passing behavior (no new red/green cycle
expected there); every user-story phase after it adds genuinely new behavior and follows
tests-first.

**Organization**: Tasks are grouped by user story (US1 = P1, US2 = P2, US3 = P3) to enable
independent implementation and testing of each. The startup-configuration-validation
requirement (FR-010/SC-005, added mid-spec) is cross-cutting — not tied to any one user story —
and gets its own phase before Polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root (unchanged from
003/005/006/007/008).

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Extract the shared upload-staging/drafting plumbing both routes need, and extend
the `LLMProvider` interface — before any user story touches the merged route.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Add `extract_document_text(self, image_bytes: bytes, image_media_type: str) ->
      str` as a new abstract method on `LLMProvider` in `src/vacancy_radar/llm/base.py`, with a
      docstring per contracts/llm-provider-extract-text.md (plain-text vision transcription,
      used only to drive retrieval for image uploads — not JSON-structured, no OCR fallback).
- [X] T002 [P] Add `build_extract_document_text_vision_prompt() -> str` to
      `src/vacancy_radar/llm/prompts.py` — instructs the model to transcribe/summarize the job
      posting's key text content from the attached image, plainly (no JSON wrapper), for
      internal retrieval use only.
- [X] T003 In `src/vacancy_radar/api.py`: extract a `StagedUpload` `NamedTuple` (`token: str`,
      `filename: str`, `document_text: str`, `image_bytes: bytes | None`,
      `image_media_type: str | None`) and a `_stage_and_read_upload(file: UploadFile) ->
      StagedUpload | str` function from `ingest_draft()`'s existing filename-check/staging/
      extraction logic (returns the existing "Unsupported file type..." message string on an
      unsupported extension, a `StagedUpload` otherwise). Update `ingest_draft()` to call it.
      Behavior must stay byte-for-byte identical — do not change any message text or condition.
- [X] T004 In `src/vacancy_radar/api.py`: extract `_draft_metadata(staged: StagedUpload,
      llm_provider: LLMProvider) -> tuple[DraftVacancyMetadata | None, str | None]` from
      `ingest_draft()`'s existing drafting try/except+messaging logic (the "couldn't read any
      text"/image-specific/generic-failure messages, unchanged). Update `ingest_draft()` to call
      it. Behavior must stay byte-for-byte identical.
- [X] T005 Run `pytest` and confirm every existing test in `tests/test_ingest_upload.py` still
      passes unchanged after T003/T004's refactor (pure extraction, no behavior change).
- [X] T006 [P] Update the `FakeLLMProvider` class in `tests/test_ui.py`, the
      `FakeDraftLLMProvider` class in `tests/test_ingest_upload.py`, and any LLM test double in
      `tests/test_api.py` to implement a stub `extract_document_text(self, image_bytes,
      image_media_type) -> str` (e.g. `raise NotImplementedError("not exercised by this test
      file's fakes")`) so each remains instantiable against the now-extended `LLMProvider` ABC.
- [X] T007 Run `pytest` again and confirm the full suite still passes (T001's new abstract
      method doesn't break instantiation of any existing fake).

**Checkpoint**: Shared plumbing exists (`StagedUpload`, `_stage_and_read_upload()`,
`_draft_metadata()`, `extract_document_text()` on the interface) — no user-visible behavior has
changed yet.

---

## Phase 2: User Story 1 - Analyze a posting from the document you already have (Priority: P1) 🎯 MVP

**Goal**: Uploading a document (image/PDF/DOCX/text) on the Analyze screen produces the same
kind of match report pasting its text would.

**Independent Test**: quickstart.md Scenarios 1–2 — upload a real PDF, then a real image, and
confirm a match report appears for each.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T008 [P] [US1] In `tests/test_llm_claude.py`: `extract_document_text(image_bytes,
      "image/png")` sends a `messages[0].content` list containing a `type: "image"` block
      (base64 `data`, `media_type: "image/png"`) and a `type: "text"` block (no
      `output_config.format` — plain-text response expected); asserts the returned string
      matches the fake response's text content.
- [X] T009 [P] [US1] In `tests/test_llm_ollama.py`: `extract_document_text(image_bytes,
      "image/png")` sends a request whose message includes an `images` list containing the
      base64-encoded bytes (via `_chat()`); asserts the returned string matches the fake
      response's plain-text content.
- [X] T010 [P] [US1] In `tests/test_ui.py`: `POST /analyze` with an uploaded `.txt` file (no
      `jd_text`) returns `_report.html` containing the same kind of report content (score,
      flags) that posting the equivalent text as `jd_text` would produce; asserts
      `documents.extract_text` (not `extract_document_text`) was used for this non-image case.
- [X] T011 [P] [US1] In `tests/test_ui.py`: `POST /analyze` with an uploaded `.png` file calls
      `llm_provider.extract_document_text` (not `documents.extract_text`) to obtain the
      analysis query text, and the resulting report reflects that extracted text having been
      used for retrieval.

### Implementation for User Story 1

- [X] T012 [US1] Implement `extract_document_text()` in `ClaudeProvider`
      (`src/vacancy_radar/llm/claude.py`): base64-encode `image_bytes`, call
      `messages.create()` with an image + text content list (prompt from
      `build_extract_document_text_vision_prompt()`), **no** `output_config` (plain-text
      response) — return the response's text block directly; catch `anthropic.APIError` →
      `LLMProviderError`.
- [X] T013 [US1] Implement `extract_document_text()` in `OllamaProvider`
      (`src/vacancy_radar/llm/ollama.py`): base64-encode `image_bytes`, call
      `self._chat(prompt, images=[image_b64])` (prompt from
      `build_extract_document_text_vision_prompt()`) and return its plain-text result directly
      — `_chat()` already raises `LLMProviderError` on HTTP failure, no additional try/except
      needed.
- [X] T014 [US1] In `src/vacancy_radar/api.py`, add `_query_text_for_analysis(staged:
      StagedUpload, llm_provider: LLMProvider) -> tuple[str | None, str | None]`: if
      `staged.image_bytes is not None`, call `extract_document_text(staged.image_bytes,
      staged.image_media_type)`, catching `LLMProviderError` into an image-specific "couldn't
      read this image directly — image-based analysis isn't available with the current setup"
      message; otherwise, return `staged.document_text` if non-empty, else `None` with a
      "Couldn't read any text from this document to analyze." message.
- [X] T015 [US1] Extend `ui_analyze()` in `src/vacancy_radar/api.py` to accept an optional `file:
      UploadFile | None = File(None)` parameter. When `file` is given and has a non-empty
      filename: call `_stage_and_read_upload(file)` (render `_error.html` directly if it returns
      a string), then `_query_text_for_analysis(staged, llm_provider)`; if query text was
      obtained, call the existing `run_analysis(query_text, retriever, llm_provider)` inside the
      same try/except the paste-text branch already uses. Render `_report.html` with
      `report`/`report_message` in context (draft/save context fields added in User Story 2).
      When `file` is absent/empty, fall through to the existing paste-text branch unchanged.
- [X] T016 [US1] Extend `src/vacancy_radar/templates/_report.html`: wrap the existing report
      body in `{% if report %}...{% endif %}`, adding `{% elif report_message %}<p
      class="error">{{ report_message }}</p>{% endif %}` immediately after, so a missing/failed
      report renders its own specific message instead of the "nothing to show yet" fallback
      (which remains correct only when a real, empty `report` exists).
- [X] T017 [US1] Extend `src/vacancy_radar/templates/index.html`: add
      `hx-encoding="multipart/form-data"` to the existing form and an `<input type="file"
      name="file">` alongside the `<textarea name="jd_text">`.

**Checkpoint**: Uploading a PDF/DOCX/text/image on the Analyze screen produces a match report —
independently testable and valuable even before User Story 2 adds inline saving.

---

## Phase 3: User Story 2 - Save the vacancy right where you analyzed it (Priority: P2)

**Goal**: The match report and drafted company/position/date fields appear together after an
upload, and confirming saves the vacancy without a second visit or re-upload.

**Independent Test**: quickstart.md Scenarios 3–4 — upload a document, edit the drafted fields,
type an outcome, confirm, and verify a new vacancy folder exists; verify report/draft failures
don't block each other.

### Tests for User Story 2 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T018 [P] [US2] In `tests/test_ui.py`: after `POST /analyze` with an uploaded file, the
      response body also contains the drafted company/position/date fields (the same markup
      `_ingest_draft.html` renders) and an `upload_token`.
- [X] T019 [P] [US2] In `tests/test_ui.py`: taking that response's `upload_token` and posting it
      (with edited fields + an outcome) to the existing `POST /ingest/confirm` route creates a
      new vacancy folder — confirming the save path is the unchanged, already-tested route (no
      new save route exists to test).
- [X] T020 [P] [US2] In `tests/test_ui.py`: with a fake LLM provider whose
      `draft_vacancy_metadata` raises but whose `analyze`/`extract_document_text` succeed (and
      the reverse case), assert both the report and the draft-or-message section render
      independently — neither is empty/missing because of the other's failure (FR-007).

### Implementation for User Story 2

- [X] T021 [US2] Extend `ui_analyze()` in `src/vacancy_radar/api.py`'s upload branch: also call
      `_draft_metadata(staged, llm_provider)`, and pass `draft`, `message`, `upload_token`
      (`staged.token`), `original_filename` (`staged.filename`), and `step` (`"review" if draft
      else "error"`) into `_report.html`'s context alongside `report`/`report_message`.
- [X] T022 [US2] Extend `src/vacancy_radar/templates/_report.html`: add a trailing `{% if
      upload_token %}<hr/><h2>Log this vacancy</h2>{% include "_ingest_draft.html" %}{% endif
      %}` block.

**Checkpoint**: Uploading a document shows the report and a ready-to-save draft together; saving
uses the exact same `/ingest/confirm` behavior as the standalone Log-a-vacancy screen.

---

## Phase 4: User Story 3 - Pasting text still just gives a report (Priority: P3)

**Goal**: The paste-text path is provably unchanged by everything User Story 1/2 added.

**Independent Test**: quickstart.md Scenario 5 — paste text, confirm only the report appears.

### Tests for User Story 3 ⚠️

> Write this test FIRST — at this point in the plan it functions as a regression guard against
> User Story 1/2's changes to the shared `ui_analyze()` function and `_report.html` template.

- [X] T023 [US3] In `tests/test_ui.py`: `POST /analyze` with only `jd_text` (no file) returns
      `_report.html` with no `upload_token` present in the response body — the "Log this
      vacancy" block must not appear.

### Implementation for User Story 3

- [X] T024 [US3] Review `ui_analyze()`'s paste-text branch in `src/vacancy_radar/api.py`: confirm
      it never passes `upload_token`/`draft`/`message`/`report_message` into `_report.html`'s
      context (only `report`) — adjust if T015/T021's changes accidentally leaked any of those
      keys into that branch.

**Checkpoint**: Paste-text behavior is provably identical to before this feature.

---

## Phase 5: Startup LLM Configuration Validation (FR-010 / SC-005)

**Goal**: The server refuses to start — with a specific, actionable message — when the
configured LLM provider is missing required configuration, instead of starting normally and
failing later with an opaque error on first use.

**Independent Test**: quickstart.md Scenario 6 — start the server with `LLM_PROVIDER=claude` and
no `ANTHROPIC_API_KEY`; confirm it fails immediately with a specific message, and that
`LLM_PROVIDER=ollama` starts normally with no key set.

### Tests ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T025 [P] In `tests/test_api.py` (or a new `tests/test_startup_config.py`): with
      `monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)` and
      `monkeypatch.setenv("LLM_PROVIDER", "claude")`, entering `with TestClient(app) as
      client:` raises an exception whose message names `ANTHROPIC_API_KEY`.
- [X] T026 [P] Same file: with `monkeypatch.setenv("LLM_PROVIDER", "ollama")` (regardless of
      `ANTHROPIC_API_KEY`), entering `with TestClient(app) as client:` does **not** raise.

### Implementation

- [X] T027 In `src/vacancy_radar/api.py`: add `validate_llm_provider_config() -> None` per
      contracts/startup-config-validation.md — raises `RuntimeError` with a message naming
      `ANTHROPIC_API_KEY` and explaining it's required when `LLM_PROVIDER` resolves to
      `"claude"` (the default) and the env var is unset/empty; no check when it resolves to
      `"ollama"`.
- [X] T028 In `src/vacancy_radar/api.py`: add an `@asynccontextmanager async def
      lifespan(app: FastAPI)` that calls `validate_llm_provider_config()` before `yield`; pass
      `lifespan=lifespan` to the existing `FastAPI(title=..., version=...)` constructor call.

**Checkpoint**: A missing required credential is caught once, at startup, with a specific
message — never discovered mid-request.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T029 [P] Update `README.md`: note that the Analyze screen (`GET /`) now also accepts a
      document upload (same formats as Log-a-vacancy) producing a report and an inline "log this
      vacancy" option, and that the server validates required LLM provider configuration at
      startup.
- [X] T030 [P] Update `CHANGELOG.md`'s `[Unreleased]` section: `### Added` — analyzing an
      uploaded document (image/PDF/DOCX/text) on the Analyze screen, with the drafted vacancy
      fields shown alongside the report so it can be logged without a second upload; startup
      validation that the configured LLM provider has its required configuration (e.g.
      `ANTHROPIC_API_KEY`), refusing to start with a specific message if not.
- [X] T031 Run `ruff check .` and fix any lint findings across all files changed by this feature.
- [X] T032 Run the full `pytest` suite and confirm all tests pass (existing + new).
- [X] T033 Perform manual quickstart validation per
      `specs/009-analyze-and-log-vacancy/quickstart.md` (all 6 scenarios) against a real
      configured backend, including a non-vision-capable Ollama model for Scenario 4.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. BLOCKS all user stories.
- **User Story 1 (Phase 2)**: Depends on Phase 1. No dependency on US2/US3.
- **User Story 2 (Phase 3)**: Depends on Phase 1 and on US1's `ui_analyze()` upload branch
  existing (T015) — it extends the same branch rather than adding a new one.
- **User Story 3 (Phase 4)**: Depends on US1 and US2 being complete — it's a regression guard
  against exactly what they changed, not new functionality of its own.
- **Startup Config Validation (Phase 5)**: Depends only on Phase 1 (nothing else) — genuinely
  independent of US1/2/3, could be implemented in parallel with them if desired.
- **Polish (Phase 6)**: Depends on all of the above being complete.

### Within Each Phase

- T003 before T004 (both edit `ingest_draft()`; T004 assumes T003's `StagedUpload` exists).
- T005 (verification) after T003/T004.
- T006 (fakes) can happen any time after T001 lands, independent of T003–T005.
- T012/T013 (provider implementations) depend on T001/T002 (interface + prompt) from
  Foundational.
- T014 depends on T012/T013 existing (calls `extract_document_text()`).
- T015 depends on T003 (`_stage_and_read_upload`) and T014 (`_query_text_for_analysis`).
- T016/T017 (templates) can proceed in parallel with T012–T015 (different files), but the
  feature isn't testable end-to-end until all of T012–T017 land.
- T021 depends on T004 (`_draft_metadata`) and T015 (the upload branch it extends).

### Parallel Opportunities

- T001, T002 (Foundational, different files) — run in parallel.
- T006 (Foundational, three different test files' fake updates) — each sub-edit is independent.
- T008, T009, T010, T011 (US1 tests, different test files/independent assertions) — run in
  parallel.
- T012, T013 (US1, different provider files) — run in parallel.
- T018, T019, T020 (US2 tests) — run in parallel.
- T025, T026 (Phase 5 tests) — run in parallel.
- T029, T030 (Polish docs) — run in parallel.
- Phase 5 (Startup Config Validation) as a whole can run in parallel with Phases 2–4, since it
  only depends on Phase 1.

---

## Parallel Example: Phase 1 (Foundational)

```bash
Task: "Add extract_document_text() abstract method to src/vacancy_radar/llm/base.py"
Task: "Add build_extract_document_text_vision_prompt() to src/vacancy_radar/llm/prompts.py"
```

## Parallel Example: User Story 1 tests

```bash
Task: "extract_document_text vision-content test in tests/test_llm_claude.py"
Task: "extract_document_text images-field test in tests/test_llm_ollama.py"
Task: "uploaded .txt file produces a report, in tests/test_ui.py"
Task: "uploaded image uses extract_document_text not documents.extract_text, in tests/test_ui.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (shared plumbing, interface extension).
2. Complete Phase 2: User Story 1.
3. **STOP and VALIDATE**: quickstart.md Scenarios 1–2 — uploading a document already produces a
   report, which is the feature's core new capability, even before inline saving exists.
4. User Story 2 is what removes the "still have to go re-upload on /ingest to log it" friction —
   valuable, but User Story 1 alone already delivers SC-001.

### Incremental Delivery

1. Foundational → US1 (validate Scenarios 1–2) → US2 (validate Scenarios 3–4) → US3 (validate
   Scenario 5, regression) → Startup Config Validation (validate Scenario 6, can be done any time
   after Foundational) → Polish (full regression, real-backend manual pass).
2. Each phase leaves the app in a fully working, deployable state.

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to its user story for traceability.
- Verify each new-behavior test fails before implementing against it (Phase 1's refactor tasks
  are the one exception — they preserve existing behavior, not add new).
- Stop at each checkpoint to validate independently before moving on.
