---

description: "Task list for Ingestion CLI feature implementation"
---

# Tasks: Ingestion CLI

**Input**: Design documents from `/specs/001-ingestion-cli/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli-commands.md](./contracts/cli-commands.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle V ("Test & Lint Gates") makes test coverage for
ingestion/upsert logic non-negotiable for this project, not optional.

**Organization**: Tasks are grouped by user story (US1/US2/US3, matching spec.md's P1/P2/P3) to
enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to the repository root

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/`, `data/example/` at repository root, per
plan.md's Structure Decision.

---

## Phase 1: Setup (Fixture Data)

**Purpose**: Populate `data/example/` with real sanitized fixture data so every user story's
independent test and every automated test in this feature has something concrete to ingest.
`data/example/README.md` already documents this data is populated "in M2" — this is that work.

- [x] T001 [P] Create CV bullet fixture(s) directly under `data/example/` (e.g.
      `data/example/experience.md`), a handful of sanitized markdown bullet points, matching
      `CV_DIR=./data/example` in `.env.example`
- [x] T002 [P] Create 2 valid vacancy folders under `data/example/vacancies/` following the
      `YYYY-MM-DD_company-slug_position-slug` naming convention, each with a `vacancy.yaml`
      (company/position/date/outcome, differing outcomes e.g. `applied` and `rejected`) plus a
      `sources/` file and a `correspondence/` file, per data-model.md's Vacancy folder entity
- [x] T003 [P] Create 1 intentionally malformed vacancy folder under
      `data/example/vacancies/` — valid folder name, but `vacancy.yaml` missing a required
      field (e.g. no `outcome`) — fixture for FR-008
- [x] T004 [P] Create 1 intentionally misnamed vacancy folder under
      `data/example/vacancies/` (doesn't match the natural-key pattern) — fixture for FR-008
- [x] T005 [P] Create 2 vacancy folders under `data/example/vacancies/` whose `vacancy.yaml`
      `company`/`position`/`date` resolve to the same natural key despite different folder
      names — fixture for FR-009 conflict detection

**Checkpoint**: `data/example/` has real fixture data for every downstream test to use.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks every user story's ingestion logic depends on.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T006 [P] Implement `ChromaStore` wrapper (`get_or_create_collection`, `upsert`, `delete`,
      `count`) around `chromadb.PersistentClient(path=".cache/chroma")` in
      `src/vacancy_radar/chroma_store.py`, per research.md's Chroma access pattern decision
- [x] T007 [P] Add `VacancyRecord` Pydantic model (`company: str`, `position: str`,
      `date: date`, `outcome: str`, `model_config = ConfigDict(extra="allow")`) to
      `src/vacancy_radar/models.py`, per data-model.md's VacancyRecord entity
- [x] T008 [P] Implement `SentenceTransformersEmbedder.embed()` in
      `src/vacancy_radar/embedder.py` (lazy-load the model on first call, batch-embed the given
      texts, cache the loaded model on `self._model`)
- [x] T009 [P] Implement `IngestManifest` load/save (JSON at `.cache/ingest-manifest.json`:
      `compat_stamp` + per-file `{content_hash, chunk_ids}` map) in
      `src/vacancy_radar/manifest.py`, per data-model.md's IngestManifest entity
- [x] T010 Implement natural-key folder validation + `vacancy.yaml`
      parsing/validation in `src/vacancy_radar/ingest.py` (regex
      `^\d{4}-\d{2}-\d{2}_[a-z0-9-]+_[a-z0-9-]+$`, parse via `VacancyRecord`, return a
      valid/invalid-with-reason result) — depends on T007
- [x] T011 Implement per-`doc_type` chunking helper in
      `src/vacancy_radar/ingest.py` (`vacancy.yaml` → 1 chunk `vacancy_meta`; each file under
      `sources/` → 1 chunk `posting`; each file under `correspondence/` → 1 chunk
      `correspondence`; `analysis.md` if present → 1 chunk `analysis`; all tagged with
      company/position/date/outcome), per research.md's chunking strategy decision — depends
      on T010

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - First-time ingest populates the local index (Priority: P1) 🎯 MVP

**Goal**: `vacancy-radar ingest` populates `experience_bullets` and `vacancies` from
`CV_DIR`/`VACANCY_DIR`, reporting a summary, tolerating empty dirs and malformed folders.

**Independent Test**: Point `CV_DIR`/`VACANCY_DIR` at `data/example/`, run `vacancy-radar
ingest` against an empty cache, and confirm both collections are populated correctly and the
summary reports the fixture folders from T003/T004/T005 as invalid/conflicting rather than
crashing.

### Tests for User Story 1

- [x] T012 [P] [US1] Test `ingest_experience_bullets()` embeds every bullet from the T001
      fixture into `experience_bullets` in `tests/test_ingest.py`
- [x] T013 [P] [US1] Test `ingest_vacancies()` embeds the T002 valid folders tagged with
      correct company/position/date/outcome metadata, reports the T003/T004 folders as invalid
      with a reason, and reports the T005 pair as conflicting, in `tests/test_ingest.py`
- [x] T014 [P] [US1] Test `vacancy-radar ingest` end-to-end against `data/example/` — exit code
      0, summary counts match the fixtures — in `tests/test_cli_ingest.py`

### Implementation for User Story 1

- [x] T015 [US1] Implement `ingest_experience_bullets(cv_dir)` in
      `src/vacancy_radar/ingest.py`: parse markdown bullets, embed via `Embedder`, full-replace
      the `experience_bullets` collection via `ChromaStore` — depends on T006, T008
- [x] T016 [US1] Implement `ingest_vacancies(vacancy_dir)` full-ingest path in
      `src/vacancy_radar/ingest.py`: walk `vacancy_dir`, validate each folder (T010), chunk
      (T011), embed, upsert into `vacancies` keyed by natural key, write manifest entries
      (T009), collect created/invalid/conflicting counts — depends on T006, T008, T010, T011,
      T009
- [x] T017 [US1] Wire the `ingest` subcommand in `src/vacancy_radar/cli.py` to call T015 + T016
      and print the run summary (bullets ingested; vacancies created/invalid/conflicting with
      folder + reason), per contracts/cli-commands.md and FR-006 — depends on T015, T016
- [x] T018 [US1] Handle empty/missing `CV_DIR`/`VACANCY_DIR` as a valid zero-item result (exit
      0, zero counts) rather than an error, in `src/vacancy_radar/ingest.py` — depends on T015,
      T016 (FR-007)

**Checkpoint**: User Story 1 is fully functional and independently testable — `vacancy-radar
ingest` works end-to-end against `data/example/`.

---

## Phase 4: User Story 2 - Incremental sync after adding or editing a vacancy (Priority: P2)

**Goal**: `vacancy-radar sync` re-embeds only new/changed vacancy files (via the manifest),
always fully replaces `experience_bullets`, and never reconciles deleted/renamed folders.

**Independent Test**: Ingest `data/example/` once, add a new vacancy folder and edit one
existing `vacancy.yaml`'s outcome, run `sync`, and confirm only those two folders were
re-embedded while the rest are reported as skipped.

### Tests for User Story 2

- [x] T019 [P] [US2] Test the manifest correctly flags an unchanged file as stale=false and a
      content-modified file as stale=true, in `tests/test_manifest.py`
- [x] T020 [P] [US2] Test `ingest_vacancies(vacancy_dir, incremental=True)` skips unchanged
      folders, embeds a newly added folder, and re-embeds only the changed file within an
      edited folder, in `tests/test_ingest.py`
- [x] T021 [P] [US2] Test `vacancy-radar sync` end-to-end: new folder → created, edited outcome
      → updated, untouched folders → skipped, deleted folder → entry remains stale (FR-011),
      in `tests/test_cli_ingest.py`
- [x] T022 [P] [US2] Test that changing `EMBEDDING_MODEL` between runs makes the next `sync`
      auto-trigger a full reindex instead of an incremental sync, in `tests/test_cli_ingest.py`
      (quickstart.md Scenario 5)

### Implementation for User Story 2

- [x] T023 [US2] Add an `incremental: bool` mode to `ingest_vacancies()` in
      `src/vacancy_radar/ingest.py`: consult the manifest's per-file `content_hash`, skip
      unchanged files, re-embed/upsert only new or changed files, update the manifest entry —
      depends on T016, T009
- [x] T024 [US2] Ensure `ingest_experience_bullets()` is safely re-runnable as a full replace
      on every `sync` call (delete-then-reinsert `experience_bullets`, no manifest tracking for
      bullets), per FR-012 — depends on T015
- [x] T025 [US2] Add a `compat.needs_reindex()` check at the top of the shared ingestion
      entrypoint in `src/vacancy_radar/ingest.py`: if the stored `compat_stamp` (from the
      manifest) doesn't match `compat.CURRENT_STAMP`, force a full (non-incremental) run this
      time and rewrite the stamp afterward — depends on T009, existing `src/vacancy_radar/compat.py`
- [x] T026 [US2] Wire the `sync` subcommand in `src/vacancy_radar/cli.py` to call the
      incremental path (T023, T024, T025) and print the run summary including a
      `vacancies_skipped` count — depends on T023, T024, T025

**Checkpoint**: User Stories 1 AND 2 both work independently — `sync` correctly does
incremental work on top of a prior `ingest`.

---

## Phase 5: User Story 3 - Full rebuild from source (Priority: P3)

**Goal**: `vacancy-radar reindex` deletes the local cache and manifest and rebuilds them from
source, without ever touching `CV_DIR`/`VACANCY_DIR`.

**Independent Test**: Ingest `data/example/`, delete/corrupt `.cache/`, run `reindex`, and
confirm the rebuilt collections match what a fresh `ingest` would produce, with zero changes to
the fixture source files.

### Tests for User Story 3

- [x] T027 [P] [US3] Test `reindex()` deletes `.cache/chroma` and `.cache/ingest-manifest.json`
      and rebuilds collections matching a fresh `ingest`'s counts, in
      `tests/test_cli_ingest.py`
- [x] T028 [P] [US3] Test that running `reindex` leaves every file under `data/example/`
      byte-identical (hash comparison before/after), in `tests/test_cli_ingest.py`

### Implementation for User Story 3

- [x] T029 [US3] Implement `reindex(cv_dir, vacancy_dir)` in `src/vacancy_radar/ingest.py`:
      delete `.cache/chroma/` and `.cache/ingest-manifest.json`, then call the full (non-
      incremental) ingest path from Phase 3 — depends on T015, T016, T009
- [x] T030 [US3] Wire the `reindex` subcommand in `src/vacancy_radar/cli.py` to call T029 and
      print the same run-summary shape as `ingest` — depends on T029

**Checkpoint**: All three user stories are independently functional — `ingest`, `sync`, and
`reindex` all work per their contracts.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required by the constitution before this feature is done.

- [x] T031 [P] Run `ruff check .` and fix any lint findings across all new/changed files
      (Constitution V)
- [x] T032 [P] Run `pytest` and confirm all tests in `tests/test_ingest.py`,
      `tests/test_manifest.py`, `tests/test_cli_ingest.py`, and the existing `tests/test_api.py`
      pass (Constitution V)
- [x] T033 Manually run every scenario in [quickstart.md](./quickstart.md) against
      `data/example/` and confirm the described expected results
- [x] T034 [P] Update the README.md roadmap checkbox: mark "Ingestion CLI" as done

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately, all tasks parallelizable
- **Foundational (Phase 2)**: Can start alongside Setup (different files); BLOCKS all user
  stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1 has no dependency on US2/US3
  - US2 depends on US1's `ingest_vacancies()`/`ingest_experience_bullets()` existing (extends
    them with `incremental=True`), so implement in priority order: US1 → US2 → US3
  - US3 depends on US1's full-ingest path existing (reindex calls it) — implement after US1
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tests are written first and must fail before implementation begins
- Foundational helpers (T006-T011) before any story-specific implementation
- Story complete and checkpoint-validated before moving to the next priority

### Parallel Opportunities

- All Phase 1 fixture tasks (T001-T005) can run in parallel — different files
- All Phase 2 tasks marked [P] (T006-T009) can run in parallel — different files; T010/T011
  are sequential (same file, dependent logic)
- Within each user story, all test tasks marked [P] can run in parallel
- T031/T032/T034 in Phase 6 can run in parallel

---

## Parallel Example: Phase 1 + Phase 2

```bash
# Fixture data (Phase 1) — all parallel, different files:
Task: "Create CV bullet fixture in data/example/experience.md"
Task: "Create 2 valid vacancy folders in data/example/vacancies/"
Task: "Create 1 malformed vacancy folder in data/example/vacancies/"
Task: "Create 1 misnamed vacancy folder in data/example/vacancies/"
Task: "Create 2 conflicting-natural-key vacancy folders in data/example/vacancies/"

# Foundational modules (Phase 2) — parallel, different files:
Task: "Implement ChromaStore wrapper in src/vacancy_radar/chroma_store.py"
Task: "Add VacancyRecord model to src/vacancy_radar/models.py"
Task: "Implement SentenceTransformersEmbedder.embed in src/vacancy_radar/embedder.py"
Task: "Implement IngestManifest in src/vacancy_radar/manifest.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (fixture data)
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenario 1 + Scenario 4 (idempotency)
5. `vacancy-radar ingest` is now usable stand-alone — `/similar`/`/analyze` work (once built)
   against a manually re-run `ingest` even before `sync`/`reindex` exist

### Incremental Delivery

1. Setup + Foundational → fixtures and shared modules ready
2. Add US1 → validate independently (quickstart Scenario 1, 4) → this is the MVP
3. Add US2 → validate independently (quickstart Scenario 2, 5)
4. Add US3 → validate independently (quickstart Scenario 3)
5. Phase 6 polish → full quickstart.md pass, lint/test gates green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This feature's contracts note that `ingest` is "sync against an empty cache" and `reindex` is
  "delete cache, then ingest" — so US2 and US3 deliberately build directly on US1's functions
  rather than duplicating them; independence here means independently *testable* and
  *demonstrable*, not implemented with zero shared code (contracts/cli-commands.md, research.md)
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
