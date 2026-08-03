---

description: "Task list for Vacancy Document Upload feature implementation"
---

# Tasks: Vacancy Document Upload

**Input**: Design documents from `/specs/006-vacancy-upload/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/ingest-upload-routes.md](./contracts/ingest-upload-routes.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle V ("Test & Lint Gates") requires test coverage for
new routes, extraction logic, and the new `LLMProvider` method, same as every prior feature.

**Organization**: Tasks are grouped by user story (US1-US4, matching spec.md's P1-P4). US1/US2/US3
are all slices of the same draft→review→confirm request flow (each validates a distinct part of
it), while US4 is fully independent — it only touches the existing CLI ingestion path and shares
nothing but the extraction module.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Paths are relative to the repository root

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root, per plan.md's Structure
Decision, following [[005-minimal-ui]]'s established pattern (templates/static already mounted,
no new toolchain). LLM drafting is faked in automated tests (same dependency-injection pattern as
`/analyze`); real OCR/PDF/DOCX quality is only validated in the manual quickstart pass (Phase 8).

---

## Phase 1: Setup

- [x] T001 Add `"pypdf>=4.0"`, `"python-docx>=1.1"`, `"pytesseract>=0.3"`, `"Pillow>=10.0"` to
      `[project].dependencies`, and `"reportlab>=4.0"` to `[project.optional-dependencies].dev`
      (test-only — generates real PDF fixtures for `tests/test_documents.py`, since `pypdf` has
      no text-drawing API of its own, corrected during implementation — research.md #7) in
      `pyproject.toml`; sync the lockfile (`uv sync --extra dev` or equivalent) — research.md #2
- [x] T002 [P] Add `RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf
      /var/lib/apt/lists/*` to `Dockerfile` (system OCR dependency, not installable via pip) —
      research.md #2
- [x] T003 [P] Change `docker-compose.yml`'s `./data/user:/data/user:ro` to `./data/user:/data/user`
      (read-write); leave `./data/example:/data/example:ro` unchanged — research.md #1, confirmed
      with the user during planning

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared extraction module and the new `LLMProvider` drafting method every user
story depends on.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T004 [P] Create `src/vacancy_radar/documents.py`: `extract_text(path: Path) -> str`
      dispatching by file extension — `.pdf` via `pypdf` (text-layer extraction), `.docx` via
      `python-docx` (paragraph text), `.png`/`.jpg`/`.jpeg` via `pytesseract` + `Pillow` (OCR),
      `.txt`/`.md` via a plain `path.read_text()` — returns `""` (never raises) when extraction
      yields no usable text, so callers can degrade gracefully per FR-008 — research.md #2, #7
- [x] T005 [P] Add `DraftVacancyMetadata` model (`company: str`, `position: str`, `date: date`)
      to `src/vacancy_radar/models.py` — no `outcome` field, per spec.md FR-003 — data-model.md
- [x] T006 Add `draft_vacancy_metadata(document_text: str) -> DraftVacancyMetadata` as a new
      abstract method on `LLMProvider` in `src/vacancy_radar/llm/base.py` — depends on T005
- [x] T007 [P] Add `build_draft_metadata_prompt(document_text: str) -> str` and
      `DRAFT_METADATA_JSON_SCHEMA` to `src/vacancy_radar/llm/prompts.py`, matching
      `DraftVacancyMetadata`'s shape — depends on T005
- [x] T008 Implement `ClaudeProvider.draft_vacancy_metadata()` in `src/vacancy_radar/llm/claude.py`
      using `output_config={"format": {"type": "json_schema", "schema":
      DRAFT_METADATA_JSON_SCHEMA}}`, same pattern as `analyze()` — depends on T006, T007
- [x] T009 Implement `OllamaProvider.draft_vacancy_metadata()` in `src/vacancy_radar/llm/ollama.py`
      using `format: "json"` plus one retry on invalid JSON, same pattern as `analyze()` —
      depends on T006, T007

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Upload a posting/offer document instead of hand-authoring YAML (Priority: P1) 🎯 MVP

**Goal**: `GET /ingest` serves an upload form; submitting a document returns drafted
company/position/date for review.

**Independent Test**: Upload a real posting document through the screen and confirm draft
company/position/date values appear, plausibly matching the document's actual content.

### Tests for User Story 1

- [x] T010 [P] [US1] Test `extract_text()` against small fixtures synthesized at test time with
      the same libraries under test — a one-page PDF built with `pypdf`, a one-paragraph DOCX
      built with `python-docx`, a short string rendered to a PNG with `Pillow`, and a plain
      `.txt` file — in `tests/test_documents.py`
- [x] T011 [P] [US1] Test `ClaudeProvider.draft_vacancy_metadata()` parses a well-formed
      structured JSON response (faked Anthropic client) into a `DraftVacancyMetadata`, in
      `tests/test_llm_claude.py`
- [x] T012 [P] [US1] Test `OllamaProvider.draft_vacancy_metadata()` parses a JSON response (faked
      HTTP layer) into a `DraftVacancyMetadata`, retrying once on invalid JSON, in
      `tests/test_llm_ollama.py`
- [x] T013 [P] [US1] Test `GET /ingest` returns `200` and renders a file-upload form, in
      `tests/test_ingest_upload.py`
- [x] T014 [P] [US1] Test `POST /ui/ingest/draft` with a valid uploaded document (fake
      `LLMProvider` dependency override) returns `200` HTML with company/position/date
      pre-filled and a hidden `upload_token`, in `tests/test_ingest_upload.py`

### Implementation for User Story 1

- [x] T015 [US1] Create `src/vacancy_radar/templates/ingest.html`: upload form
      (`enctype="multipart/form-data"`, one file input) posting to `POST /ui/ingest/draft`
- [x] T016 [US1] Create `src/vacancy_radar/templates/_ingest_draft.html`: review form with
      `company`/`position`/`date` pre-filled and editable, an empty required `outcome` field,
      and a hidden `upload_token`, posting to `POST /ui/ingest/confirm` — depends on T005
- [x] T017 [US1] Add `GET /ingest` route in `src/vacancy_radar/api.py` rendering `ingest.html` —
      depends on T015
- [x] T018 [US1] Add `POST /ui/ingest/draft` route in `src/vacancy_radar/api.py`: accept the
      uploaded file, stage it at `.cache/pending-uploads/<uuid>/<original-filename>`, call
      `documents.extract_text()`, call `llm_provider.draft_vacancy_metadata()` — catching
      `LLMProviderError`/`ValidationError`/`json.JSONDecodeError` to render `_ingest_draft.html`
      with blank fields and a "drafting didn't work, fill in manually" message instead of
      raising (FR-008) — render `_ingest_draft.html` on success with the drafted values —
      depends on T004, T006/T008/T009, T016

**Checkpoint**: User Story 1 is fully functional and independently testable — drafting works
end-to-end (saving is User Story 2).

---

## Phase 4: User Story 2 - Review and correct the draft before it's saved (Priority: P2)

**Goal**: The maintainer can edit any drafted field and must set outcome themselves; nothing is
saved until explicitly confirmed.

**Independent Test**: Upload a document, deliberately change a drafted field before confirming,
and verify the saved `vacancy.yaml` reflects the edited value, not the original draft.

### Tests for User Story 2

- [x] T019 [P] [US2] Test `POST /ui/ingest/confirm` with an edited `position` value writes a
      `vacancy.yaml` containing the edited value, not the original drafted one, in
      `tests/test_ingest_upload.py`
- [x] T020 [P] [US2] Test `POST /ui/ingest/confirm` rejects a request with an empty/missing
      `outcome` field — no vacancy folder is created — in `tests/test_ingest_upload.py`
- [x] T021 [P] [US2] Test that never calling `POST /ui/ingest/confirm` after a draft leaves no
      vacancy folder created (only the harmless staged file under `.cache/pending-uploads/`), in
      `tests/test_ingest_upload.py`

### Implementation for User Story 2

- [x] T022 [US2] Add `POST /ui/ingest/confirm` route in `src/vacancy_radar/api.py`: validate
      every field is present (reject with a clear rendered message otherwise — note `Form("")`
      not `Form(...)`, research.md #8), compute the natural key via `ingest.natural_key()` from
      the submitted `company`/`position`/`date`, check `VACANCY_DIR/<natural-key>/` doesn't
      already exist before writing anything (pre-write conflict guard, research.md #5 /
      contracts correction — writing into an existing same-named folder would silently
      overwrite it), then create the folder, write `vacancy.yaml`, and move the staged file from
      `.cache/pending-uploads/<upload_token>/` into `<natural-key>/sources/` — depends on T018
- [x] T023 [US2] Create `src/vacancy_radar/templates/_ingest_result.html`: renders a
      success/conflict/error result message — depends on T022

**Checkpoint**: User Stories 1 AND 2 both work independently — the full draft-review-confirm
loop persists a correct `vacancy.yaml` reflecting the maintainer's final edits.

---

## Phase 5: User Story 3 - The uploaded document becomes retrievable immediately (Priority: P3)

**Goal**: A confirmed vacancy is immediately searchable via `/similar`/`/analyze`, with conflicts
surfaced rather than silently lost.

**Independent Test**: Upload and confirm a new vacancy, then immediately submit matching text to
`/similar` and confirm the new vacancy appears.

### Tests for User Story 3

- [x] T024 [P] [US3] Test that a vacancy confirmed via `POST /ui/ingest/confirm` is immediately
      returned by a matching `POST /similar` call, with no separate ingestion command run, in
      `tests/test_ingest_upload.py`
- [x] T025 [P] [US3] Test that confirming a natural-key conflict (same date+company+position as
      an already-ingested vacancy) surfaces both folders via the response, without either being
      silently overwritten or embedded, in `tests/test_ingest_upload.py`

### Implementation for User Story 3

- [x] T026 [US3] After writing the new folder in `POST /ui/ingest/confirm`, re-invoke
      `ingest.ingest_vacancies(vacancy_dir, ...)` (unchanged, reused as-is) and render the
      resulting `RunSummary` (`vacancies_created` for success, `vacancies_conflicting` for a
      conflict) via `_ingest_result.html` — depends on T022, T023

**Checkpoint**: User Stories 1, 2, AND 3 all work independently — confirmed vacancies are live
in Chroma immediately, and conflicts are surfaced rather than silently lost.

---

## Phase 6: User Story 4 - Existing folder-based ingestion accepts the same document formats (Priority: P4)

**Goal**: A PDF/DOCX/image file dropped directly into an existing vacancy folder's
`sources/`/`correspondence/` is embedded via the existing CLI, not skipped or erroring.

**Independent Test**: Manually place a PDF into an existing vacancy folder's `sources/`
directory, run the existing sync command, and confirm its text is embedded.

### Tests for User Story 4

- [x] T027 [P] [US4] Test `chunk_vacancy_folder()` embeds extracted text from a PDF, DOCX, and
      image file placed under `sources/`, instead of raising or reading raw bytes as text, in
      `tests/test_ingest.py`

### Implementation for User Story 4

- [x] T028 [US4] Update `chunk_vacancy_folder()` in `src/vacancy_radar/ingest.py` to call
      `documents.extract_text()` for recognized non-text extensions (`.pdf`, `.docx`, `.png`,
      `.jpg`, `.jpeg`) instead of `file_path.read_text()`; every other extension keeps the
      existing plain-text read path unchanged — depends on T004

**Checkpoint**: All four user stories are independently functional — both ways of logging a
vacancy (upload screen and CLI/folder) handle the same document formats consistently.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required by the constitution before this feature is done.

- [x] T029 [P] Run `ruff check .` and fix any lint findings across all new/changed files
      (Constitution V)
- [x] T030 [P] Run `pytest` and confirm all tests — including `tests/test_documents.py`,
      `tests/test_ingest_upload.py`, the extended `tests/test_llm_claude.py`/
      `tests/test_llm_ollama.py`/`tests/test_ingest.py`, and every existing test from
      [[001-ingestion-cli]] through [[005-minimal-ui]] — pass (Constitution V)
- [x] T031 Manually run every scenario in [quickstart.md](./quickstart.md) against a running
      server with the updated `docker-compose.yml`/`Dockerfile` (or bare, with `VACANCY_DIR`
      writable), a real configured LLM backend, and real PDF/DOCX/image documents — the
      automated suite fakes LLM drafting entirely and uses synthesized fixtures, so this is the
      only pass that validates real OCR/PDF/DOCX extraction quality end-to-end
- [x] T032 [P] Update `README.md`'s `POST /ingest/vacancy` Endpoints entry (the "not yet
      implemented" caveat added during [[005-minimal-ui]]'s doc audit is no longer accurate) and
      note the `data/user` mount is now read-write; add a `CHANGELOG.md` entry under
      `[Unreleased]`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup; BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 has no dependency on US2/US3/US4 and delivers the core "upload and see a draft" loop
  - US2 depends on US1's draft route/template existing — it adds the confirm route that
    persists the (possibly edited) values
  - US3 depends on US2's confirm route existing — it adds re-invoking `ingest_vacancies()` for
    immediate retrievability and conflict surfacing
  - US4 is fully independent of US1-US3 — it only touches the existing CLI ingestion path,
    sharing just the Foundational `documents.py` module
  - Implement in priority order: US1 → US2 → US3 → US4 (though US4 could be done anytime after
    Foundational, in parallel with the others, since it touches different files)
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Within Each User Story

- Tests are written first and must fail before implementation begins
- Foundational extraction/model/provider changes (T004-T009) before any story-specific route
  work
- Story complete and checkpoint-validated before moving to the next priority

### Parallel Opportunities

- T002, T003 in Setup can run in parallel with T001 and each other
- T004, T005, T007 in Foundational can run in parallel (different files); T006 depends on T005;
  T008/T009 depend on T006 and T007 but can then run in parallel with each other
- Within each user story, the test tasks marked [P] can run in parallel
- US4 (T027-T028) can be worked on in parallel with US1-US3 once Foundational is done, since it
  shares no files with the upload-route work
- T029/T030/T032 in Polish can run in parallel; T031 should run after them (it exercises the
  finished feature)

---

## Parallel Example: Phase 2 + Phase 3 tests

```bash
# Foundational (Phase 2) — independent files:
Task: "Create src/vacancy_radar/documents.py with extract_text()"
Task: "Add DraftVacancyMetadata to src/vacancy_radar/models.py"
Task: "Add build_draft_metadata_prompt() + schema to src/vacancy_radar/llm/prompts.py"

# User Story 1 tests — all parallel:
Task: "Test extract_text() against synthesized pdf/docx/image/text fixtures, in tests/test_documents.py"
Task: "Test ClaudeProvider.draft_vacancy_metadata() JSON parsing, in tests/test_llm_claude.py"
Task: "Test OllamaProvider.draft_vacancy_metadata() JSON parsing + retry, in tests/test_llm_ollama.py"
Task: "Test GET /ingest renders the upload form, in tests/test_ingest_upload.py"
Task: "Test POST /ui/ingest/draft renders drafted fields, in tests/test_ingest_upload.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1-2 restricted to just the draft step
   (upload → see drafted fields) — confirming isn't wired up yet, but the core "read a document,
   propose metadata" loop is already provable
5. This alone proves the hardest, most novel part of the feature (local extraction + LLM
   drafting) before building the persistence/conflict-handling on top

### Incremental Delivery

1. Setup + Foundational → extraction module, drafting method, and infra changes ready
2. Add US1 → validate independently (draft rendering) → hardest part proven
3. Add US2 → validate independently (edited values persisted, outcome required)
4. Add US3 → validate independently (immediately searchable, conflicts surfaced)
5. Add US4 → validate independently (CLI path accepts the same formats)
6. Phase 7 polish → full quickstart.md pass with real documents and a real LLM backend, lint/test
   gates green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- `documents.py`'s `extract_text()` is the single shared implementation both the upload routes
  and the existing CLI ingestion path call — no format-handling logic is duplicated between them
- `ingest_vacancies()` (existing, unchanged) is reused wholesale for conflict detection and
  Chroma upsert after the confirm route writes the new folder — there is exactly one place this
  logic exists, not two
- The `docker-compose.yml`/`Dockerfile` changes in Setup are a deliberate, user-confirmed
  widening of the app's write access to the maintainer's own data — see research.md #1
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
