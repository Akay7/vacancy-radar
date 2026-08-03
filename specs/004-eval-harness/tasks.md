---

description: "Task list for Eval Harness feature implementation"
---

# Tasks: Eval Harness

**Input**: Design documents from `/specs/004-eval-harness/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/eval-cli.md](./contracts/eval-cli.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle V ("Test & Lint Gates") requires test coverage for
the harness's own logic, same as every prior feature in this project.

**Organization**: Tasks are grouped by user story (US1-US4, matching spec.md's P1-P4). Each of
the four checks is genuinely independent of the other three (different golden file, different
check module, no shared runtime state) — the only thing they share is the report/fixtures/metrics
infrastructure built in Foundational and the dispatch table in `eval/run_eval.py`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Paths are relative to the repository root

## Path Conventions

Single project — `eval/`, `tests/` at repository root, per plan.md's Structure Decision. `eval/`
already exists from the M1 scaffold (`eval/run_eval.py` stub, `eval/golden/.gitkeep`) — this
feature fills it in rather than creating it from scratch. No new fixture data is reused from
`data/example/` (research.md #3 — a dedicated `eval/golden/fixtures/` set is authored instead).

---

## Phase 1: Setup

- [x] T001 Create `eval/lib/__init__.py` (empty) so `eval/run_eval.py`, invoked as `python
      eval/run_eval.py`, can import `eval/lib/*` modules as a package

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks every check depends on — report shapes, JSONL fixture
loading, metric functions, and the CLI/dispatch skeleton.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T002 [P] Create `eval/lib/report.py`: `FixtureFailure` (`fixture_id`, `kind:
      Literal["regression", "fixture_error"]`, `reason`), `CheckResult` (`name`, `status:
      Literal["pass", "fail", "skipped"]`, `metrics: dict[str, float]`, `sample_size`,
      `failures: list[FixtureFailure]`), `EvalReport` (`checks: list[CheckResult]`,
      `overall_status`) dataclasses per data-model.md, plus `render_markdown(report: EvalReport)
      -> str` producing one table row per check with name/status/sample size/metrics, and a
      failure listing per check with `kind` shown
- [x] T003 [P] Create `eval/lib/fixtures.py`: `load_jsonl(path: Path) -> list[dict]` — parses one
      JSON object per line, returns `[]` if the file doesn't exist or is empty (never raises for
      that case — callers use an empty list to set `status="skipped"` per the edge case in
      spec.md)
- [x] T004 [P] Create `eval/lib/metrics.py`: `recall_at_k(expected_ids: list[str], retrieved_ids:
      list[str], k: int) -> float`, `mrr(expected_ids_per_query: list[list[str]],
      retrieved_ids_per_query: list[list[str]]) -> float`, `precision_at_k(expected_ids:
      list[str], retrieved_ids: list[str], k: int) -> float`, `wilson_score_interval(successes:
      int, n: int, z: float = 1.96) -> tuple[float, float]` — pure functions, stdlib `math` only,
      no new dependency (research.md #4)
- [x] T005 Replace the `raise NotImplementedError("M5")` stub in `eval/run_eval.py` with the real
      CLI skeleton per contracts/eval-cli.md: `argparse` with a repeatable `--check
      {grounding,bullets,similar,filter-consistency}` option (omitted = run all four), a
      dispatch dict mapping check name to a `() -> CheckResult` callable (populated by each user
      story below — starts empty), assembling an `EvalReport`, printing
      `report.render_markdown()`, and `sys.exit(0)` when every requested check's status is
      `"pass"`/`"skipped"`, else `sys.exit(1)` — depends on T002

**Checkpoint**: Foundation ready — user story implementation can now begin, in any order.

---

## Phase 3: User Story 1 - Grounding enforcement check (Priority: P1) 🎯 MVP

**Goal**: `python eval/run_eval.py --check grounding` runs `grounding.enforce()` against every
labeled fixture in `eval/golden/grounding.jsonl` and reports whether each fabricated claim was
rejected and each genuine claim was kept.

**Independent Test**: With only `eval/golden/grounding.jsonl` present (no ingestion, no other
golden files needed), run `python eval/run_eval.py --check grounding` and confirm it reports
pass/fail per fixture and an aggregate score on its own.

### Tests for User Story 1

- [x] T006 [P] [US1] Test `render_markdown()` renders a table row with a check's name, status,
      sample size, and metrics, and lists failing fixtures with their `kind`, for a hand-built
      `EvalReport`, in `tests/test_eval_report.py`
- [x] T007 [P] [US1] Test `load_jsonl()` returns parsed dicts for a well-formed temp file and
      `[]` for a missing/empty path, in `tests/test_eval_fixtures.py`
- [x] T008 [P] [US1] Test `eval/lib/grounding_check.py`'s check function against small inline
      fixtures (not the real golden file): a fixture where every `expect_grounded` label matches
      `grounding.enforce()`'s actual keep/drop outcome yields `status="pass"`; one mismatch
      yields `status="fail"` with that fixture in `failures` as `kind="regression"`; a fixture
      whose flag cites an unknown `source_id` while labeled `expect_grounded=True` is reported as
      `kind="fixture_error"` instead (data-model.md's validation rule) — in
      `tests/test_eval_checks.py`

### Implementation for User Story 1

- [x] T009 [US1] Create `eval/lib/grounding_check.py`: `run(golden_path=Path("eval/golden/
      grounding.jsonl")) -> CheckResult` — loads fixtures via `fixtures.load_jsonl`, for each line
      builds `CandidateFlag`/`CandidateSentence`/`CandidateReport` objects (stripping the
      fixture-only `expect_grounded` key first) and a `sources` dict, calls
      `grounding.enforce()`, compares each flag/sentence's actual kept-or-not against its
      `expect_grounded` label, applies a 100%-accuracy threshold (`GROUNDING_MIN_ACCURACY = 1.0`
      — Principle II is non-negotiable), and returns a `CheckResult` with per-fixture
      `FixtureFailure`s distinguishing `regression` from `fixture_error` — depends on T002, T003
- [x] T010 [US1] Wire `"grounding"` into `eval/run_eval.py`'s dispatch dict — depends on T005, T009
- [x] T011 [US1] Author `eval/golden/grounding.jsonl` with ~8-10 hand-curated fixtures per
      data-model.md's schema: a verbatim-quote match kept, a fabricated quote dropped, a
      case/whitespace-insensitive match kept, the bracket-prefix-echo case (`"[bullet-0] ..."` —
      the real bug found and fixed during [[003-analyze-report-generation]]'s manual validation,
      preserved here as a permanent regression fixture), an unknown-`source_id` case dropped, and
      an empty-source-registry case — depends on T009 (format must match what `run()` expects)

**Checkpoint**: User Story 1 is fully functional and independently testable.

---

## Phase 4: User Story 2 - Retrieval recall/MRR check (Priority: P2)

**Goal**: `python eval/run_eval.py --check bullets` ingests a small dedicated CV fixture into a
disposable eval-only Chroma index, runs each labeled query through `Retriever.query_bullets()`,
and reports recall@5 and MRR.

**Independent Test**: Run `python eval/run_eval.py --check bullets` on its own — it ingests its
own fixture data and reports recall@5/MRR without touching `.cache/chroma` or needing any other
golden file.

### Tests for User Story 2

- [x] T012 [P] [US2] Test `recall_at_k()` and `mrr()` against small hand-computed
      expected/retrieved id lists (including the case where an expected id never appears in
      retrieved results), in `tests/test_eval_metrics.py`
- [x] T013 [P] [US2] Test `eval/lib/retrieval_check.py`'s check function using the
      `BagOfWordsEmbedder` test fake ([[002-similar-retrieval]]'s `tests/_fakes.py`) against a
      tiny in-memory fixture set: confirms recall@5/MRR are computed correctly, and a fixture
      whose `expected_bullet_ids` references an id that was never actually ingested is reported
      as `kind="fixture_error"`, in `tests/test_eval_checks.py`

### Implementation for User Story 2

- [x] T014 [US2] Create `eval/lib/retrieval_check.py`: `run(golden_path=Path("eval/golden/
      bullets.jsonl"), fixtures_cv_dir=Path("eval/golden/fixtures/cv"),
      chroma_path=".cache/eval-chroma") -> CheckResult` — ingests `fixtures_cv_dir` via
      `ingest.ingest_experience_bullets()` pointed at the eval-only Chroma path (never
      `.cache/chroma`), loads `bullets.jsonl`, queries `Retriever.query_bullets(query, top_k=5)`
      per fixture, computes recall@5 and MRR via `metrics.py`, and reports a fixture whose
      expected id never appears among the ingested bullet ids as `kind="fixture_error"` — depends
      on T002, T003, T004
- [x] T015 [US2] Wire `"bullets"` into `eval/run_eval.py`'s dispatch dict — depends on T005, T014
- [x] T016 [US2] Author `eval/golden/fixtures/cv/experience.md` (~8 bullets spanning a spread of
      skills/domains) and `eval/golden/bullets.jsonl` (~5-6 labeled queries referencing those
      bullets' resulting `bullet-{i}` ids) — depends on T014
- [x] T017 [US2] Run the check against the real `SentenceTransformersEmbedder` (not the test
      fake) with the fixtures from T016, observe the actual recall@5/MRR scores, and set
      `BULLET_RECALL_AT_5_MIN` in `retrieval_check.py` accordingly — same empirical-calibration
      approach as `retriever.py`'s `MIN_SIMILARITY` (research.md #5) — depends on T016

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Similar-vacancy precision check (Priority: P3)

**Goal**: `python eval/run_eval.py --check similar` ingests a small dedicated vacancy fixture set
into the eval-only Chroma index, runs each labeled query posting through
`Retriever.query_similar_vacancies()`, and reports precision@3.

**Independent Test**: Run `python eval/run_eval.py --check similar` on its own — it ingests its
own fixture vacancies and reports precision@3 without needing the other three golden files.

### Tests for User Story 3

- [x] T018 [P] [US3] Test `precision_at_k()` against hand-computed cases (all top-k relevant, none
      relevant, a mix), in `tests/test_eval_metrics.py`
- [x] T019 [P] [US3] Test `eval/lib/similar_check.py`'s check function using the
      `BagOfWordsEmbedder` fake against a tiny in-memory fixture set: confirms precision@3 is
      computed correctly, and a fixture whose `expected_similar_ids` references a natural key
      never ingested is reported as `kind="fixture_error"`, in `tests/test_eval_checks.py`

### Implementation for User Story 3

- [x] T020 [US3] Create `eval/lib/similar_check.py`: `run(golden_path=Path("eval/golden/
      similar.jsonl"), fixtures_vacancies_dir=Path("eval/golden/fixtures/vacancies"),
      chroma_path=".cache/eval-chroma") -> CheckResult` — ingests `fixtures_vacancies_dir` via
      `ingest.ingest_vacancies()` pointed at the eval-only Chroma path, loads `similar.jsonl`,
      queries `Retriever.query_similar_vacancies(query_posting, top_k=3)` per fixture, computes
      precision@3 via `metrics.py`, and reports an unknown expected id as `kind="fixture_error"`
      — depends on T002, T003, T004
- [x] T021 [US3] Wire `"similar"` into `eval/run_eval.py`'s dispatch dict — depends on T005, T020
- [x] T022 [US3] Author `eval/golden/fixtures/vacancies/` (3-4 small vacancy folders, valid
      `vacancy.yaml` + `sources/posting.md` each, natural-key-named per
      [[001-ingestion-cli]]'s convention) and `eval/golden/similar.jsonl` (2-3 labeled query
      postings with their truly-similar natural keys) — depends on T020
- [x] T023 [US3] Run the check against the real `SentenceTransformersEmbedder` with the fixtures
      from T022, observe the actual precision@3 scores, and set `SIMILAR_PRECISION_AT_3_MIN` in
      `similar_check.py` accordingly (research.md #5) — depends on T022

**Checkpoint**: User Stories 1, 2, AND 3 all work independently.

---

## Phase 6: User Story 4 - Filter-rule consistency check (Priority: P4)

**Goal**: `python eval/run_eval.py --check filter-consistency` runs each fixture's single
filter-rules citation through `grounding.enforce()` and reports accuracy with a confidence
interval, not a bare percentage.

**Independent Test**: Run `python eval/run_eval.py --check filter-consistency` on its own — no
ingestion needed, and it doesn't depend on any of the other three golden files.

### Tests for User Story 4

- [x] T024 [P] [US4] Test `wilson_score_interval()` against known reference bounds (e.g. n=10
      successes=10 gives a tight high interval; n=10 successes=5 gives a wide interval centered
      near 0.5), in `tests/test_eval_metrics.py`
- [x] T025 [P] [US4] Test `eval/lib/filter_consistency_check.py`'s check function against small
      inline fixtures: a real filter-rule citation correctly kept, a fabricated one correctly
      rejected, both reported with accuracy + interval in `metrics`; a fixture whose flag's
      `source_id` isn't `"filter-rules"` is reported as `kind="fixture_error"` — in
      `tests/test_eval_checks.py`

### Implementation for User Story 4

- [x] T026 [US4] Create `eval/lib/filter_consistency_check.py`: `run(golden_path=Path("eval/
      golden/filter-consistency.jsonl")) -> CheckResult` — loads fixtures, for each one builds
      `sources={"filter-rules": filter_rules_text}` and a single-`CandidateFlag`
      `CandidateReport`, calls `grounding.enforce()`, compares the flag's kept-or-not against
      `expect_grounded`, computes accuracy and `wilson_score_interval()` via `metrics.py`, applies
      a 100%-accuracy threshold (`FILTER_CONSISTENCY_MIN_ACCURACY = 1.0`), and reports any
      fixture whose flag doesn't cite `source_id="filter-rules"` as `kind="fixture_error"` —
      depends on T002, T003, T004
- [x] T027 [US4] Wire `"filter-consistency"` into `eval/run_eval.py`'s dispatch dict — depends on
      T005, T026
- [x] T028 [US4] Author `eval/golden/filter-consistency.jsonl` with ~8-10 fixtures: several real
      violations correctly cited verbatim, several fabricated citations not present in the stated
      `filter_rules_text`, and a case/whitespace-variant match — depends on T026

**Checkpoint**: All four checks are independently functional — the full suite is complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required by the constitution before this feature is done.

- [x] T029 [P] Add a `python eval/run_eval.py` step to `.github/workflows/ci.yml`, after the
      existing `pytest` step, so a failing check fails the same CI job (FR-006, SC-004,
      research.md #6)
- [x] T030 [P] Run `ruff check .` and fix any lint findings across all new/changed files
      (Constitution V)
- [x] T031 [P] Run `pytest` and confirm all tests — including the new `tests/test_eval_*.py`
      files and every existing test from [[001-ingestion-cli]], [[002-similar-retrieval]], and
      [[003-analyze-report-generation]] — pass (Constitution V)
- [x] T032 Manually run every scenario in [quickstart.md](./quickstart.md), including deliberately
      breaking `grounding.enforce()`'s verbatim check to confirm the grounding check actually
      fails (SC-003) before reverting — this is the one pass that exercises the real
      `eval/run_eval.py` script and its exit codes end-to-end, not just its unit-tested internals
- [x] T033 [P] Update the README.md roadmap checkbox: mark "Eval harness" as done

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup; BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1, US2, US3, US4 have no dependencies on each other and can be implemented in any order —
    each has its own golden file, its own check module, and (for US2/US3) its own fixture data
  - Priority order (P1 → P2 → P3 → P4) is the recommended implementation order, matching
    spec.md's stated priorities (grounding first — Principle II is non-negotiable)
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Within Each User Story

- Tests are written first and must fail before implementation begins
- Check-module implementation before dispatch-table wiring before fixture authoring
  (fixture authoring must match the format the check module actually expects)
- US2/US3's threshold-calibration task depends on their own fixture-authoring task, since it
  needs real observed scores to calibrate against

### Parallel Opportunities

- T002, T003, T004 in Foundational can run in parallel (different files); T005 depends on T002
- Within each user story, the two/three test tasks marked [P] can run in parallel
- Once Foundational is done, all four user stories' *check-module* tasks (T009, T014, T020,
  T026) could be worked on in parallel by different people — but each story's *dispatch-wiring*
  task (T010, T015, T021, T027) edits the same file, `eval/run_eval.py`, so those four should be
  applied one at a time even if the check modules themselves were built concurrently
- T029/T030/T031/T033 in Polish can run in parallel; T032 should run after them (it exercises the
  finished script)

---

## Parallel Example: Phase 2 + Phase 3 tests

```bash
# Foundational (Phase 2) — independent files:
Task: "Create eval/lib/report.py (FixtureFailure/CheckResult/EvalReport + render_markdown)"
Task: "Create eval/lib/fixtures.py (load_jsonl)"
Task: "Create eval/lib/metrics.py (recall_at_k, mrr, precision_at_k, wilson_score_interval)"

# User Story 1 tests — all parallel:
Task: "Test render_markdown() table/failure rendering, in tests/test_eval_report.py"
Task: "Test load_jsonl() well-formed/missing-file behavior, in tests/test_eval_fixtures.py"
Task: "Test grounding_check.run() pass/fail/fixture_error paths, in tests/test_eval_checks.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenario 1 restricted to `--check grounding`, and
   Scenario 2 (the SC-003 regression-catching proof) — the single most important guarantee this
   feature exists to protect is already enforceable in CI at this point
5. The grounding gate alone is deployable/usable value — Constitution II compliance now has a
   standing regression check, even before retrieval/similarity/filter-consistency checks exist

### Incremental Delivery

1. Setup + Foundational → shared report/fixture/metric infrastructure and CLI skeleton ready
2. Add US1 → validate independently (quickstart Scenarios 1-2, `--check grounding`) → grounding
   gate live
3. Add US2 → validate independently (`--check bullets`)
4. Add US3 → validate independently (`--check similar`)
5. Add US4 → validate independently (`--check filter-consistency`)
6. Phase 7 polish → CI wiring, full quickstart.md pass, lint/test gates green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- All four checks are fully local and deterministic — no live LLM call, no network access, in
  any of them (Constitution I/III, FR-004) — this is what makes CI gating (T029) possible at all
- `grounding.enforce()` and the retrieval/ingestion functions it reuses are unmodified by this
  feature — the eval harness is a new *consumer* of existing, already-tested production code, not
  a change to it
- Commit after each task or logical group
- Stop at any checkpoint to validate a check independently
