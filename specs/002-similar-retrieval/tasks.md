---

description: "Task list for `/similar` Retrieval feature implementation"
---

# Tasks: `/similar` Retrieval

**Input**: Design documents from `/specs/002-similar-retrieval/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/similar-endpoint.md](./contracts/similar-endpoint.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle V ("Test & Lint Gates") makes test coverage for
retrieval logic non-negotiable for this project, not optional.

**Organization**: Tasks are grouped by user story (US1/US2/US3, matching spec.md's P1/P2/P3) to
enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to the repository root

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root, per plan.md's Structure
Decision. Reuses `data/example/` fixtures already created by [[001-ingestion-cli]] — no new
fixture data needed.

---

## Phase 1: Setup

**Purpose**: The one-line change needed before any retrieval work is meaningful — see
research.md's distance-metric decision.

- [x] T001 Bump `compat.CURRENT_STAMP.schema_version` (e.g. `"1"` → `"2"`) in
      `src/vacancy_radar/compat.py`, so the existing compat-stamp auto-reindex check (built in
      [[001-ingestion-cli]]) picks up the new cosine-space `vacancies` collection on the next
      `ingest`/`sync`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks every user story's retrieval logic depends on.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T002 Extend `ChromaStore` in `src/vacancy_radar/chroma_store.py`: add an optional
      `metadata` parameter to `get_or_create_collection()` (and thread it through `upsert()`
      and `reset_collection()`), and add a `query(collection, query_embeddings, n_results,
      where=None, metadata=None) -> dict` method wrapping the underlying Chroma collection's
      `.query()`, per research.md's Chroma access decisions
- [x] T003 Add `VACANCIES_COLLECTION_METADATA = {"hnsw:space": "cosine"}` next to
      `VACANCIES_COLLECTION` in `src/vacancy_radar/ingest.py`, and pass it to this collection's
      existing `store.upsert(...)` and `store.reset_collection(...)` call sites so the
      collection is always created with cosine space regardless of whether ingestion or
      retrieval touches it first — depends on T002
- [x] T004 [P] Extend `SimilarVacancy` in `src/vacancy_radar/models.py`: rename `title` →
      `position`, add `excerpt: str` and `is_duplicate: bool`, per data-model.md

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - See similar past vacancies with their outcomes (Priority: P1) 🎯 MVP

**Goal**: `POST /similar` returns a ranked list of the most similar previously-ingested
vacancies (company/position/outcome/similarity/excerpt), comparing only `doc_type=posting`
chunks, filtered to meaningful matches.

**Independent Test**: Ingest `data/example/`, paste JD text nearly identical to the Acme Corp
posting, call `/similar`, and confirm that vacancy comes back first with its correct
company/position/outcome and a high similarity score.

### Tests for User Story 1

- [x] T005 [P] [US1] Test `Retriever.query_similar_vacancies()` returns a near-duplicate JD's
      matching vacancy first, with correct company/position/outcome/similarity, in
      `tests/test_retriever.py`
- [x] T006 [P] [US1] Test `query_similar_vacancies()` only compares `doc_type=posting` chunks —
      a JD matching a fixture's `correspondence`/`vacancy_meta` text content should not produce
      a match on that basis alone, in `tests/test_retriever.py`
- [x] T007 [P] [US1] Test `query_similar_vacancies()` orders results most-to-least similar when
      multiple fixture vacancies are relevant, in `tests/test_retriever.py`
- [x] T008 [P] [US1] Test `POST /similar` end-to-end against `data/example/` returns `200` with
      the expected `SimilarVacancy` shape (company/position/outcome/similarity/excerpt), in
      `tests/test_api.py`

### Implementation for User Story 1

- [x] T009 [US1] Implement the core of `Retriever.query_similar_vacancies()` in
      `src/vacancy_radar/retriever.py`: embed the JD text, query the `vacancies` collection
      with `where={"doc_type": "posting"}` and an over-fetch `n_results` (`top_k * 4`, capped
      at 20), group hits by natural key (`chunk_id.split("/", 1)[0]`) keeping the
      best-scoring chunk per key, and sort by similarity — depends on T002, T003
- [x] T010 [US1] Apply the `MIN_SIMILARITY = 0.5` threshold and truncate to `top_k` in
      `src/vacancy_radar/retriever.py` (FR-007) — depends on T009
- [x] T011 [US1] Build each match's `excerpt` (first 280 chars of the matched chunk's stored
      document text, `…`-truncated if longer) in `src/vacancy_radar/retriever.py` (FR-009) —
      depends on T009
- [x] T012 [US1] Wire `POST /similar` in `src/vacancy_radar/api.py`: add a `get_retriever()`
      FastAPI dependency (`Depends`) returning a `Retriever()`, call
      `query_similar_vacancies(jd_text)`, and return `list[SimilarVacancy]` via
      `response_model` — depends on T009, T010, T011, T004

**Checkpoint**: User Story 1 is fully functional and independently testable — `/similar`
returns ranked, thresholded matches with excerpts.

---

## Phase 4: User Story 2 - Flag likely duplicate applications (Priority: P2)

**Goal**: A match on the same company + effectively the same position is distinctly flagged
(`is_duplicate: true`), separate from the generic similarity ranking.

**Independent Test**: Paste JD text for the same company and role as an already-ingested
vacancy, call `/similar`, and confirm that match has `is_duplicate: true`; paste JD text for
the same company but a different role and confirm it does NOT get flagged.

### Tests for User Story 2

- [x] T013 [P] [US2] Test a match with similarity at/above `DUPLICATE_SIMILARITY` (0.85) has
      `is_duplicate=True`, in `tests/test_retriever.py`
- [x] T014 [P] [US2] Test a same-company-different-role match (similarity below
      `DUPLICATE_SIMILARITY` but still above `MIN_SIMILARITY`) has `is_duplicate=False`, in
      `tests/test_retriever.py`
- [x] T015 [P] [US2] Test `POST /similar` surfaces `"is_duplicate": true` for a near-identical
      JD paste against a `data/example/` fixture, in `tests/test_api.py`

### Implementation for User Story 2

- [x] T016 [US2] Add the `DUPLICATE_SIMILARITY = 0.85` constant and compute `is_duplicate` for
      each match in `src/vacancy_radar/retriever.py` (FR-008) — depends on T009

**Checkpoint**: User Stories 1 AND 2 both work independently — duplicate matches are
distinctly flagged on top of the ranked results.

---

## Phase 5: User Story 3 - Graceful cold-start / no-match result (Priority: P3)

**Goal**: An empty index or a JD with no meaningful matches returns a valid empty result, never
an error; empty/whitespace-only JD text is rejected as invalid input.

**Independent Test**: Call `/similar` against an empty vector index, and separately with
unrelated JD text against a populated index, and confirm both return `200 []`; call `/similar`
with empty `jd_text` and confirm `422`.

### Tests for User Story 3

- [x] T017 [P] [US3] Test `query_similar_vacancies()` against an empty `vacancies` collection
      returns `[]`, not an error, in `tests/test_retriever.py`
- [x] T018 [P] [US3] Test `query_similar_vacancies()` with JD text unrelated to any fixture
      returns `[]` (everything below `MIN_SIMILARITY`), in `tests/test_retriever.py`
- [x] T019 [P] [US3] Test `POST /similar` returns `200 []` against an empty index, in
      `tests/test_api.py`
- [x] T020 [P] [US3] Test `POST /similar` with empty or whitespace-only `jd_text` returns `422`,
      in `tests/test_api.py`

### Implementation for User Story 3

- [x] T021 [US3] Ensure `query_similar_vacancies()` handles zero candidates (empty collection or
      nothing above threshold) by returning `[]` in `src/vacancy_radar/retriever.py` — depends
      on T009, T010
- [x] T022 [US3] Add empty/whitespace `jd_text` validation (raise `422`) in the `/similar` route
      in `src/vacancy_radar/api.py` (FR-005) — depends on T012

**Checkpoint**: All three user stories are independently functional — `/similar` handles the
happy path, the duplicate-flag case, and cold-start/no-match/invalid-input cases correctly.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required by the constitution before this feature is done.

- [x] T023 [P] Run `ruff check .` and fix any lint findings across all new/changed files
      (Constitution V)
- [x] T024 [P] Run `pytest` and confirm all tests in `tests/test_retriever.py`,
      `tests/test_api.py`, and the existing ingestion-CLI test files still pass (Constitution V)
- [x] T025 Manually run every scenario in [quickstart.md](./quickstart.md) against a running API
      server and `data/example/`, using the real embedding model (not the test fake), and
      confirm the described expected results
- [x] T026 [P] Update the README.md roadmap checkbox: mark "`/similar` retrieval" as done

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Can start alongside Setup; BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1 has no dependency on US2/US3
  - US2 depends on US1's `query_similar_vacancies()` core (T009) existing — adds the
    `is_duplicate` field on top of it
  - US3 depends on US1's core (T009, T010) existing — adds graceful empty/no-match handling
    and input validation on top of it
  - Implement in priority order: US1 → US2 → US3
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tests are written first and must fail before implementation begins
- Foundational helpers (T002-T004) before any story-specific implementation
- Story complete and checkpoint-validated before moving to the next priority

### Parallel Opportunities

- T004 in Phase 2 can run in parallel with T002/T003 (different file)
- Within each user story, all test tasks marked [P] can run in parallel
- T023/T024/T026 in Phase 6 can run in parallel

---

## Parallel Example: Phase 2 + Phase 3 tests

```bash
# Foundational (Phase 2) — T004 is independent of T002/T003:
Task: "Extend SimilarVacancy model in src/vacancy_radar/models.py"

# User Story 1 tests — all parallel, different assertions in the same or different files:
Task: "Test near-duplicate JD returns matching vacancy first, in tests/test_retriever.py"
Task: "Test only doc_type=posting chunks are compared, in tests/test_retriever.py"
Task: "Test results ordered most-to-least similar, in tests/test_retriever.py"
Task: "Test POST /similar end-to-end shape, in tests/test_api.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (compat-stamp bump)
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1, 2, 5, 6
5. `/similar` is now usable stand-alone for its core "have I seen this before" value, even
   before the duplicate-flag refinement exists

### Incremental Delivery

1. Setup + Foundational → shared modules and collection config ready
2. Add US1 → validate independently (quickstart Scenarios 1, 2) → this is the MVP
3. Add US2 → validate independently (quickstart Scenarios 3, 4)
4. Add US3 → validate independently (quickstart Scenarios 5, 6)
5. Phase 6 polish → full quickstart.md pass, lint/test gates green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This feature is purely additive on top of [[001-ingestion-cli]] — no existing ingestion
  behavior changes except the cosine-space collection metadata (T001, T003), which is picked
  up automatically via the existing compat-stamp mechanism rather than a new migration path
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
