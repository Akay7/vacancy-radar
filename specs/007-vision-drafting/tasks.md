---

description: "Task list for Vision-Based Image Drafting"
---

# Tasks: Vision-Based Image Drafting

**Input**: Design documents from `/specs/007-vision-drafting/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/llm-provider-vision.md, quickstart.md

**Tests**: Included — this repo's established pattern (every prior feature: 003/005/006) is
tests-first, and Constitution V requires test coverage for new logic.

**Organization**: Tasks are grouped by user story (US1 = P1, US2 = P2) to enable independent
implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root (unchanged from 003/005/006).

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Remove local OCR and lay the shared plumbing both user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Remove `pytesseract>=0.3` and `Pillow>=10.0` from `[project].dependencies` in
      `pyproject.toml` (both were added in 006 solely for OCR — confirmed unused elsewhere).
- [X] T002 [P] Remove the `apt-get install tesseract-ocr` step (and its comment) from
      `Dockerfile`.
- [X] T003 Remove `_extract_image()` and the `pytesseract`/`PIL`/`Image` imports from
      `src/vacancy_radar/documents.py`; change the image branch in `extract_text()` to
      `if suffix in IMAGE_EXTENSIONS: return ""` (no local extraction — see research.md #2).
      Add `IMAGE_MEDIA_TYPES` mapping (`.png` → `"image/png"`, `.jpg`/`.jpeg` → `"image/jpeg"`)
      to the same file.
- [X] T004 [P] In `tests/test_documents.py`: delete `test_extract_text_from_image_via_ocr` and
      its `_make_image()` helper (and the now-unused `PIL`/`ImageDraw` import); add
      `test_extract_text_returns_empty_string_for_image` asserting `extract_text()` returns
      `""` for a `.png`/`.jpg` path (no OCR); add a test asserting `IMAGE_MEDIA_TYPES` has an
      entry for every key in `IMAGE_EXTENSIONS`.
- [X] T005 [P] Extend `LLMProvider.draft_vacancy_metadata()`'s abstract signature in
      `src/vacancy_radar/llm/base.py` with optional `image_bytes: bytes | None = None` and
      `image_media_type: str | None = None` parameters; update the docstring to describe the
      vision-only-for-images contract (image given → vision attempt or `LLMProviderError`; no
      text-based fallback, per contracts/llm-provider-vision.md).
- [X] T006 [P] Add `build_draft_metadata_vision_prompt() -> str` (no `document_text` parameter
      needed — there is no OCR hint to include) to `src/vacancy_radar/llm/prompts.py`,
      instructing the model to extract company/position/date from the image, leaving a field
      as `""` rather than guessing when the image doesn't state it (same non-fabrication rule
      as the existing text prompt).
- [X] T007 Update the `FakeLLMProvider` test doubles' `draft_vacancy_metadata` stub signatures
      in `tests/test_api.py` and `tests/test_ui.py` to accept
      `image_bytes=None, image_media_type=None` so they remain instantiable against the
      extended abstract method.

**Checkpoint**: Foundation ready — OCR is gone, user story implementation can now begin.

---

## Phase 2: User Story 1 - Accurate drafts from a photo or screenshot (Priority: P1) 🎯 MVP

**Goal**: When a vision-capable backend is configured, drafted company/position/date come from
the LLM's own reading of the uploaded image — and remain fully reviewable/editable before
saving.

**Independent Test**: quickstart.md Scenario 1 — upload a real, imperfect photo of a posting
with a vision-capable backend configured; confirm the drafted fields are at least as accurate
as, and typically more accurate than, the old OCR-based drafting was, and every field is still
editable.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T008 [P] [US1] In `tests/test_llm_claude.py`: calling `draft_vacancy_metadata("",
      image_bytes=..., image_media_type="image/png")` sends a `messages[0].content` list
      containing a `type: "image"` block (base64 `data`, `media_type: "image/png"`) and a
      `type: "text"` block, using `output_config.format` with `DRAFT_METADATA_JSON_SCHEMA`;
      assert the parsed `DraftVacancyMetadata` matches a well-formed fake response.
- [X] T009 [P] [US1] In `tests/test_llm_ollama.py`: calling `draft_vacancy_metadata("",
      image_bytes=..., image_media_type="image/png")` sends a request payload whose message
      includes an `images` list containing the base64-encoded bytes; assert the parsed result
      matches a well-formed fake response.
- [X] T010 [P] [US1] In `tests/test_ui.py`: uploading an image never calls
      `documents.extract_text` (patch/spy it and assert it isn't called for an image upload)
      and always calls `llm_provider.draft_vacancy_metadata` with non-`None`
      `image_bytes`/`image_media_type` — the LLM call is never skipped for images.

### Implementation for User Story 1

- [X] T011 [US1] Implement the vision request path in `ClaudeProvider.draft_vacancy_metadata()`
      (`src/vacancy_radar/llm/claude.py`): when `image_bytes` is given, base64-encode it and
      call `messages.create()` with an image + text content list (prompt from
      `build_draft_metadata_vision_prompt()`) and the existing `DRAFT_METADATA_JSON_SCHEMA`
      `output_config`; parse and return exactly as the existing text path does, including the
      today-date default for a blank `date`.
- [X] T012 [US1] Implement the vision request path in `OllamaProvider.draft_vacancy_metadata()`
      (`src/vacancy_radar/llm/ollama.py`): extend `_chat()` with an optional
      `images: list[str] | None = None` parameter forwarded into the request JSON body only
      when provided; when `image_bytes` is given, base64-encode it, build the prompt via
      `build_draft_metadata_vision_prompt()`, and call `_chat(prompt, images=[image_b64])`.
- [X] T013 [US1] Update `ingest_draft()` in `src/vacancy_radar/api.py`: for uploads whose suffix
      is in `documents.IMAGE_EXTENSIONS`, read the staged file's raw bytes and look up
      `documents.IMAGE_MEDIA_TYPES[suffix]`; pass `document_text=""` (skip calling
      `documents.extract_text()` for images entirely — it always returns `""` now) plus
      `image_bytes=`/`image_media_type=` to `llm_provider.draft_vacancy_metadata()`; change the
      skip-condition to `if not document_text and image_bytes is None:` so an image upload
      always attempts drafting.

**Checkpoint**: US1 is independently functional — a vision-capable backend now drafts from the
image itself, and the draft is still fully reviewable before saving.

---

## Phase 3: User Story 2 - Clear signal when vision isn't available (Priority: P2)

**Goal**: A non-vision backend, or a vision attempt that errors partway through, produces a
specific, plain-language message telling the maintainer image-based drafting isn't available —
never a generic error, never a silent empty draft — and manual entry still saves successfully.

**Independent Test**: quickstart.md Scenarios 2 & 3.

### Tests for User Story 2 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T014 [P] [US2] In `tests/test_llm_claude.py`: when the vision-path request raises (e.g.
      `anthropic.APIStatusError` or `anthropic.APIConnectionError`), `draft_vacancy_metadata()`
      raises `LLMProviderError` — assert exactly **one** `messages.create()` call was made (no
      second/fallback request).
- [X] T015 [P] [US2] In `tests/test_llm_ollama.py`: when the vision-path `_chat()` call raises
      (e.g. `httpx.ConnectError`), `draft_vacancy_metadata()` raises `LLMProviderError` — assert
      no fallback `_chat()` retry was made.
- [X] T016 [P] [US2] In `tests/test_ui.py`: when `llm_provider.draft_vacancy_metadata` raises
      `LLMProviderError` for an **image** upload, the rendered `_ingest_draft.html` `message`
      is the specific "this backend can't read images / image-based drafting isn't available"
      wording — distinct from the existing generic message used for non-image failures (assert
      the two messages differ and the image one names the actual limitation).

### Implementation for User Story 2

- [X] T017 [US2] In `ClaudeProvider.draft_vacancy_metadata()`, wrap the vision-path call in a
      `try/except` catching `anthropic.APIError`, `anthropic.APIConnectionError`,
      `json.JSONDecodeError`, and `pydantic.ValidationError`, re-raising as `LLMProviderError`
      (matching the existing text-path error handling) — no fallback attempt, since
      `document_text` is always `""` for images.
- [X] T018 [US2] Apply the equivalent `try/except` (catching `httpx.HTTPError` /
      `json.JSONDecodeError` / `pydantic.ValidationError`) around the vision-path call in
      `OllamaProvider.draft_vacancy_metadata()`, re-raising as `LLMProviderError`.
- [X] T019 [US2] In `ingest_draft()` (`src/vacancy_radar/api.py`), when `image_bytes is not
      None` and `draft_vacancy_metadata()` raises `LLMProviderError`/`ValidationError`/
      `json.JSONDecodeError`, render a specific message ("Your configured LLM backend couldn't
      read this image directly — image-based drafting isn't available with the current setup.
      Fill in every field manually below, or switch to a vision-capable model.") instead of the
      existing generic non-image failure message.

**Checkpoint**: Both user stories are independently functional and tested — vision-based
drafting works where supported, and every failure mode produces a clear, specific message.

---

## Phase 4: Polish & Cross-Cutting Concerns

- [X] T020 [P] Update `CHANGELOG.md`'s `[Unreleased]` section: `Added` — image uploads now
      draft from the LLM's own reading of the image; `Removed` — local OCR (`pytesseract`,
      `Pillow`), no longer used or needed for any upload type.
- [X] T021 [P] Update `README.md`'s Stack table: change the "Document extraction" row's
      description to reflect `pypdf`/`python-docx` for PDF/DOCX plus vision-based drafting
      (not local OCR) for images; no architecture-diagram node changes needed (`documents.py`
      still sits between `upload` and `llm`, it just does less for images now).
- [X] T022 Run `ruff check .` and fix any lint findings across all files changed by this
      feature.
- [X] T023 Run the full `pytest` suite and confirm all tests pass (existing + new, with the
      OCR-specific test removed).
- [X] T024 Perform manual quickstart validation per `specs/007-vision-drafting/quickstart.md`
      (all 4 scenarios) against a real vision-capable backend and a real non-vision Ollama
      model — including confirming the Docker image builds successfully without
      `tesseract-ocr` installed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. BLOCKS both user stories.
- **User Story 1 (Phase 2)**: Depends on Phase 1. No dependency on US2.
- **User Story 2 (Phase 3)**: Depends on Phase 1 and on US1's vision-path code existing
  (T011/T012) — there's nothing to wrap a `try/except` around otherwise. Its tests (T014-T016)
  are written first per the tests-first rule and will fail until Phase 3's implementation
  lands.
- **Polish (Phase 4)**: Depends on both user stories being complete.

### Within Each Phase

- T001-T003 (dependency/documents.py removal) before T004 (documents.py tests) — the tests
  assert the *new* behavior.
- T005 (`base.py` signature) before any provider implementation (T011, T012).
- T006 (`prompts.py`) before T011/T012 (both call it).
- Provider vision-path implementation (T011/T012) before the error-wrapping tasks (T017/T018).
- `api.py` wiring (T013, T019) can proceed once T005 (signature) and T007 (fakes) land, in
  parallel with the provider implementations themselves.

### Parallel Opportunities

- T001, T002 (dependency/Dockerfile removal) touch different files — run in parallel.
- T005, T006 (Phase 1, different files) — run in parallel.
- T008, T009, T010 (US1 tests) touch different test files — run in parallel.
- T014, T015, T016 (US2 tests) touch different test files — run in parallel.
- T020, T021 (Polish docs) touch different files — run in parallel.

---

## Parallel Example: Phase 1 (Foundational)

```bash
Task: "Remove pytesseract/Pillow from pyproject.toml"
Task: "Remove tesseract-ocr apt-get step from Dockerfile"
Task: "Extend LLMProvider.draft_vacancy_metadata() signature in src/vacancy_radar/llm/base.py"
Task: "Add build_draft_metadata_vision_prompt() to src/vacancy_radar/llm/prompts.py"
```

## Parallel Example: User Story 1 tests

```bash
Task: "Vision content-block test in tests/test_llm_claude.py"
Task: "images-field test in tests/test_llm_ollama.py"
Task: "extract_text-not-called-for-images test in tests/test_ui.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (OCR removal + shared plumbing).
2. Complete Phase 2: User Story 1.
3. **STOP and VALIDATE**: quickstart.md Scenario 1 against a real vision-capable backend.
4. This alone already delivers the feature's core value (SC-001) — US2 only refines the
   *messaging* on the failure path, which already degrades to manual entry without it (just
   with a generic rather than specific message).

### Incremental Delivery

1. Foundational → US1 (validate Scenario 1) → US2 (validate Scenarios 2 & 3) → Polish
   (validate Scenario 4, full regression, confirm Docker builds without `tesseract-ocr`).
2. Each phase leaves the app in a fully working state.

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to its user story for traceability.
- Verify each test fails before implementing against it.
- Stop at each checkpoint to validate independently before moving on.
