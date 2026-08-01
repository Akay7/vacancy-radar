---

description: "Task list for `/analyze` Full Report Generation feature implementation"
---

# Tasks: `/analyze` Full Report Generation

**Input**: Design documents from `/specs/003-analyze-report-generation/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/analyze-endpoint.md](./contracts/analyze-endpoint.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle V ("Test & Lint Gates") makes test coverage for
grounding/retrieval/generation logic non-negotiable for this project, not optional.

**Organization**: Tasks are grouped by user story (US1/US2/US3, matching spec.md's P1/P2/P3).
Because this feature is fundamentally **one LLM call producing one structured report**, US2 and
US3 mostly *validate* behavior already built in US1's phase rather than adding large new
implementation surface — see the Notes section at the end for why that's the honest shape of
this feature, not a shortcut.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to the repository root

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root, per plan.md's Structure
Decision. Reuses `data/example/` fixtures already created by [[001-ingestion-cli]] — no new
fixture data needed. LLM calls are faked in automated tests (dependency-injected HTTP/SDK
layer); real Claude/Ollama calls only happen in the manual quickstart pass (Phase 6).

---

## Phase 1: Setup

- [x] T001 Bump `compat.CURRENT_STAMP.schema_version` again (e.g. `"2"` → `"3"`) in
      `src/vacancy_radar/compat.py`, so the existing auto-reindex mechanism
      ([[001-ingestion-cli]]) picks up the new cosine-space `experience_bullets` collection
- [x] T002 [P] Move `httpx>=0.27` from `[project.optional-dependencies].dev` to `[project]`'s
      main `dependencies` list in `pyproject.toml` — `OllamaProvider` needs it at runtime
      (research.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks every user story depends on — bullet retrieval, the
grounding validator, the candidate-report shapes, and the filter-rules reader.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T003 Add `BULLETS_COLLECTION_METADATA = {"hnsw:space": "cosine"}` in
      `src/vacancy_radar/ingest.py`, and ensure it actually takes effect: add an explicit
      `store.get_or_create_collection(BULLETS_COLLECTION, metadata=BULLETS_COLLECTION_METADATA)`
      call at the very start of `ingest_experience_bullets()` (before `delete_all`/`upsert`
      touch it — Chroma ignores metadata on a collection that already exists, and
      `delete_all()`'s own `get_or_create_collection()` call would otherwise create it with the
      default L2 space first), and pass `metadata=BULLETS_COLLECTION_METADATA` to `reindex()`'s
      existing `store.reset_collection(BULLETS_COLLECTION)` call — depends on T001
- [x] T004 [P] In `src/vacancy_radar/models.py`: change `Report.score` from `float` to
      `Literal["strong", "good", "weak", "poor"]`; add `CandidateReport`, `CandidateFlag`
      (`label`, `severity`, `reason`, `quote`, `source_id`), and `CandidateSentence` (`text`,
      `quote`, `source_id`) per data-model.md
- [x] T005 [P] Create `src/vacancy_radar/filter_rules.py`: `load_filter_rules(path=Path("data/user/filter-rules.md")) -> str`
      returning the file's text if present, `""` if absent (FR-007)
- [x] T006 [P] Create `src/vacancy_radar/grounding.py`: `enforce(candidate: CandidateReport,
      sources: dict[str, str]) -> Report`-shaped result (flags, gaps, draft_paragraph,
      citations) — for each `CandidateFlag`/`CandidateSentence`, check `quote` is a
      whitespace/case-normalized substring of `sources[source_id]`; drop it if the `source_id`
      is unknown or the quote doesn't match (FR-008); build `draft_paragraph` by
      space-joining only the surviving `CandidateSentence.text` values, in original order;
      collect one `Citation` per surviving flag/sentence — depends on T004
- [x] T007 Implement `Retriever.query_bullets(query_text, top_k=5)` in
      `src/vacancy_radar/retriever.py`: embed `query_text`, cosine-query
      `experience_bullets` (no `doc_type` filter — bullets aren't tagged with one), return up
      to `top_k` results **with no similarity threshold** (research.md — thresholding is a
      `/similar` user-facing concern, not an internal retrieval-augmentation one) — depends on
      T003

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Grounded match assessment (Priority: P1) 🎯 MVP

**Goal**: `POST /analyze` returns a match band, red/green flags, and gaps — every flag citing a
real retrieved bullet or filter rule, verified by the shared grounding validator.

**Independent Test**: Ingest `data/example/`, paste a JD that clearly overlaps with some
ingested bullets and clearly lacks others, call `/analyze`, and confirm the score/flags/gaps
reflect that overlap and every flag's citation actually appears in the cited source.

### Tests for User Story 1

- [x] T008 [P] [US1] Test `grounding.enforce()` drops a flag whose `quote` doesn't appear in
      any source and keeps one whose `quote` does, in `tests/test_grounding.py`
- [x] T009 [P] [US1] Test `Retriever.query_bullets()` returns up to `top_k` bullets ranked by
      similarity to a query, using the `BagOfWordsEmbedder` test fake
      ([[002-similar-retrieval]]'s `tests/_fakes.py`), in `tests/test_retriever.py`
- [x] T010 [P] [US1] Test `ClaudeProvider.analyze()` parses a well-formed structured JSON
      response (via a faked Anthropic client) into a `CandidateReport`, in
      `tests/test_llm_claude.py`
- [x] T011 [P] [US1] Test `OllamaProvider.analyze()` parses a JSON response (via a faked HTTP
      layer) into a `CandidateReport`, and retries once with a corrective follow-up if the
      first response isn't valid JSON, in `tests/test_llm_ollama.py`
- [x] T012 [P] [US1] Test `POST /analyze` end-to-end against `data/example/` (LLMProvider
      dependency-overridden with a fake returning a known `CandidateReport`) — confirms the
      response's flags/gaps reflect the fake's output post-grounding, in `tests/test_api.py`

### Implementation for User Story 1

- [x] T013 [US1] Create `src/vacancy_radar/llm/prompts.py`: `build_analyze_prompt(jd_text,
      bullets: list[tuple[str, str]], filter_rules_text: str) -> str` — one shared prompt
      (JD + retrieved bullets with their ids + filter rules text + the four-dimension rubric:
      required skills present, experience-level match, domain/industry match, evidenced
      impact) used by both providers, instructing the model to return the `CandidateReport`
      JSON shape with `quote`/`source_id` on every flag and draft sentence — depends on T005,
      T007
- [x] T014 [US1] Implement `ClaudeProvider.analyze()` in `src/vacancy_radar/llm/claude.py`:
      call `client.messages.create(..., output_config={"format": {"type": "json_schema",
      "schema": ...}})` with the prompt from T013, parse the returned JSON into a
      `CandidateReport` — depends on T013, T004
- [x] T015 [US1] Implement `OllamaProvider.analyze()` in `src/vacancy_radar/llm/ollama.py`:
      POST to `{self.host}/api/chat` (or `/api/generate`) with the prompt from T013 instructing
      JSON-only output, `json.loads()` the response, retry once with a "return only valid JSON"
      follow-up on parse failure, then parse into a `CandidateReport` — depends on T013, T004
- [x] T016 [US1] Add a `get_llm_provider()` FastAPI dependency in `src/vacancy_radar/api.py`
      reading the `LLM_PROVIDER` environment variable (`claude` | `ollama`, per
      `.env.example`) and instantiating the matching provider — depends on T014, T015
- [x] T017 [US1] Wire `POST /analyze` in `src/vacancy_radar/api.py`: validate `jd_text`
      (reuse the empty/whitespace check pattern from `/similar`), call
      `Retriever.query_bullets()` and `Retriever.query_similar_vacancies()`, load filter rules
      via `filter_rules.load_filter_rules()`, build the source registry
      (`{"bullet-{i}": text, "filter-rules": filter_rules_text}`), call
      `provider.analyze(...)` to get a `CandidateReport`, run it through
      `grounding.enforce()`, assemble the final `Report` (`score=candidate.match_band`,
      `similar=` the vacancy query result), and return via `response_model=Report` — depends
      on T006, T007, T016
- [x] T018 [US1] Add error handling in the `/analyze` route: catch connection/authentication
      errors from the configured provider and raise `HTTPException(502, ...)` with a clear
      message (FR-012) — depends on T017

**Checkpoint**: User Story 1 is fully functional and independently testable — `/analyze`
returns a grounded score/flags/gaps for a real JD against `data/example/`.

---

## Phase 4: User Story 2 - Grounded draft opening paragraph (Priority: P2)

**Goal**: The same report also includes a draft opening paragraph built only from grounded
sentences — empty (not fabricated) when there's nothing to ground it in.

**Independent Test**: Call `/analyze` with a JD matching ingested bullets and confirm every
sentence of `draft_paragraph` traces to a citation; call it again against an empty index and
confirm `draft_paragraph` is `""` with no error.

### Tests for User Story 2

- [x] T019 [P] [US2] Test `grounding.enforce()` builds `draft_paragraph` by joining only
      grounded `CandidateSentence`s, in their original order, in `tests/test_grounding.py`
- [x] T020 [P] [US2] Test `POST /analyze`'s `draft_paragraph` contains only claims that also
      appear in `citations`, against `data/example/`, in `tests/test_api.py`
- [x] T021 [P] [US2] Test `POST /analyze` against an empty index (`.cache/` deleted) returns
      `200` with `draft_paragraph=""`, `flags=[]`, `citations=[]`, and non-empty `gaps` — not
      an error and not fabricated content (FR-010), in `tests/test_api.py`

### Implementation for User Story 2

- [x] T022 [US2] Based on T019-T021 results, adjust `grounding.enforce()`'s sentence-joining in
      `src/vacancy_radar/grounding.py` if needed (e.g. spacing/punctuation between sentences)
      — the empty-index case (T021) requires no new code: an empty source registry means every
      candidate flag/sentence fails validation automatically, which is already `grounding.enforce()`'s
      designed behavior from T006 — depends on T006, T017

**Checkpoint**: User Stories 1 AND 2 both work independently — the draft paragraph is
grounded exactly like the flags, including on a cold-start empty index.

---

## Phase 5: User Story 3 - Similar vacancies in the same report (Priority: P3)

**Goal**: The report's `similar` field matches what a standalone `/similar` call would return
for the same JD text.

**Independent Test**: Call `/analyze` with a JD nearly identical to an already-ingested
vacancy, and confirm `similar` matches a direct `/similar` call's result for the same text.

### Tests for User Story 3

- [x] T023 [P] [US3] Test `POST /analyze`'s `similar` field is identical in content to a direct
      `POST /similar` call with the same `jd_text`, against `data/example/`, in
      `tests/test_api.py`

### Implementation for User Story 3

- [x] T024 [US3] Verify (and adjust if T023 finds a discrepancy) that `/analyze`'s call to
      `Retriever.query_similar_vacancies(jd_text)` in `src/vacancy_radar/api.py` uses the same
      defaults `/similar` uses, so the two endpoints never disagree — depends on T017

**Checkpoint**: All three user stories are independently functional — `/analyze` delivers a
grounded assessment, a grounded draft, and consistent similar-vacancy data in one response.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required by the constitution before this feature is done.

- [x] T025 [P] Run `ruff check .` and fix any lint findings across all new/changed files
      (Constitution V)
- [x] T026 [P] Run `pytest` and confirm all tests — including
      `tests/test_grounding.py`, `tests/test_llm_claude.py`, `tests/test_llm_ollama.py`, the
      extended `tests/test_api.py`/`tests/test_retriever.py`, and every existing test from
      [[001-ingestion-cli]]/[[002-similar-retrieval]] — pass (Constitution V)
- [x] T027 Manually run every scenario in [quickstart.md](./quickstart.md) against a running
      API server, `data/example/`, and **real** configured LLM backends (both `LLM_PROVIDER=claude`
      and `LLM_PROVIDER=ollama`), confirming the described expected results — the automated
      suite fakes the LLM entirely, so this is the only pass that exercises the real grounding
      guarantee end-to-end
- [x] T028 [P] Update the README.md roadmap checkbox: mark "`/analyze` full report generation"
      as done

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Can start alongside Setup; BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1 has no dependency on US2/US3 and contains essentially all of this feature's new
    implementation surface, because one LLM call produces the whole report
  - US2 depends on US1's `/analyze` wiring (T017) existing — it validates and hardens the
    draft-paragraph slice of what US1 already built
  - US3 depends on US1's `/analyze` wiring (T017) existing — it validates the
    already-existing `query_similar_vacancies()` call is wired in consistently
  - Implement in priority order: US1 → US2 → US3
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tests are written first and must fail before implementation begins
- Foundational helpers (T003-T007) before any story-specific implementation
- Story complete and checkpoint-validated before moving to the next priority

### Parallel Opportunities

- T002 in Setup can run in parallel with T001
- T004, T005, T006 in Foundational can run in parallel (different files); T007 depends on T003
- Within US1, T008-T012 (all tests) can run in parallel; T013 is a prerequisite for T014/T015,
  which can then run in parallel with each other
- T025/T026/T028 in Polish can run in parallel

---

## Parallel Example: Phase 2 + Phase 3 tests

```bash
# Foundational (Phase 2) — independent files:
Task: "Change Report.score type + add CandidateReport shapes in src/vacancy_radar/models.py"
Task: "Create src/vacancy_radar/filter_rules.py"
Task: "Create src/vacancy_radar/grounding.py"

# User Story 1 tests — all parallel:
Task: "Test grounding.enforce() drops/keeps flags correctly, in tests/test_grounding.py"
Task: "Test query_bullets() ranking, in tests/test_retriever.py"
Task: "Test ClaudeProvider.analyze() JSON parsing, in tests/test_llm_claude.py"
Task: "Test OllamaProvider.analyze() JSON parsing + retry, in tests/test_llm_ollama.py"
Task: "Test POST /analyze end-to-end with a faked provider, in tests/test_api.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1, 6, 7 (assessment, empty JD, backend
   error) — Scenario 2 (draft paragraph) will already work since it's produced by the same
   call, but isn't the MVP's stated goal
5. `/analyze` is now usable stand-alone for its core "is this a match" value

### Incremental Delivery

1. Setup + Foundational → shared modules and collection config ready
2. Add US1 → validate independently (quickstart Scenarios 1, 6, 7) → this is the MVP
3. Add US2 → validate independently (quickstart Scenarios 2, 3)
4. Add US3 → validate independently (quickstart Scenario 4)
5. Phase 6 polish → full quickstart.md pass against real LLM backends, lint/test gates green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- This feature is one LLM call producing one structured report — US2 and US3 deliberately
  validate slices of what US1 built rather than adding large new implementation, because that
  is the actual shape of the dependency graph, not an artificial split for its own sake
  (contracts/analyze-endpoint.md, research.md)
- The grounding validator (`grounding.py`) is the single non-bypassable checkpoint for
  Constitution Principle II — both providers produce best-effort candidates; nothing reaches
  the HTTP response without passing through it first
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
