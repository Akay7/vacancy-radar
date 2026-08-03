# Implementation Plan: Eval Harness

**Branch**: `004-eval-harness` | **Date**: 2026-08-01 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-eval-harness/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Implement the `eval/run_eval.py` script already stubbed at scaffold time (M1) into a real,
fully-local eval harness that runs four independently-runnable checks — grounding enforcement,
experience-bullet retrieval (recall@5/MRR), similar-vacancy retrieval (precision@3), and
filter-rule consistency — against checked-in labeled golden fixtures under `eval/golden/`, and
reports a markdown summary plus a process exit code suitable for gating CI alongside `ruff` and
`pytest`. No live LLM call or network access is required for any check: grounding and
filter-consistency exercise `grounding.enforce()` directly against curated `CandidateReport`-
shaped fixtures, while the two retrieval checks exercise the real local embedding model and
`Retriever` against a small dedicated eval-only CV/vacancy fixture set, isolated from both the
maintainer's real data and the real `.cache/chroma`.

## Technical Context

**Language/Version**: Python 3.11 (matches the rest of the project; no new runtime).

**Primary Dependencies**: None new. Reuses `vacancy_radar.grounding` (grounding/filter-consistency
checks), `vacancy_radar.retriever.Retriever` + `vacancy_radar.embedder.SentenceTransformersEmbedder`
+ `vacancy_radar.chroma_store.ChromaStore` (retrieval checks), `vacancy_radar.ingest` (to build the
eval-only index from the eval's own fixture CV/vacancy folders). Standard library only for
JSONL parsing and the filter-consistency confidence interval (no new dependency for statistics).

**Storage**: Golden fixtures are checked-in JSONL files under `eval/golden/*.jsonl`. Retrieval
checks build a disposable, eval-only Chroma index at `.cache/eval-chroma` (gitignored, rebuilt
every run) — never the real `.cache/chroma`, never the maintainer's real `CV_DIR`/`VACANCY_DIR`.

**Testing**: `pytest` unit tests (`tests/test_eval_*.py`) for the harness's own logic — metric
computation (recall@k, MRR, precision@k, confidence interval), fixture loading/validation, and
report formatting — using small in-memory fixtures, per Constitution V. The golden-set runs
themselves (via `eval/run_eval.py`) are the feature's actual deliverable, run manually and in CI,
not part of the `pytest` suite.

**Target Platform**: Linux server / local dev machine (same as the rest of the project); runnable
in the existing GitHub Actions CI job.

**Project Type**: Single project — a standalone top-level script (`eval/run_eval.py`), matching
the scaffold's existing `eval/` directory, not part of the packaged `vacancy_radar` CLI (the
constitution and scaffold both already treat it as a separate maintainer tool, not a shipped
end-user feature).

**Performance Goals**: Full suite completes in well under a minute (SC-001) once the local
embedding model is already cached on disk — first-ever cold download of the model is a one-time
environment-setup cost shared with the rest of the project (ingestion already requires it), not
counted against this budget.

**Constraints**: No live LLM call, no network access, no dependency on or mutation of the
maintainer's real `CV_DIR`/`VACANCY_DIR` or real `.cache/chroma` (FR-004, FR-008).

**Scale/Scope**: A handful to a few dozen hand-curated fixtures per golden set — enough to be a
meaningful regression corpus, small enough to stay hand-maintainable (Constitution IV, YAGNI).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | Eval harness reads only its own checked-in `eval/golden/` fixtures (fake data, like `data/example/`) — never `data/user/`. | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | This feature *is* the constitution-mandated grounding check ("the eval harness (grounding check is a required eval, not optional)") — implements it as User Story 1. | PASS |
| III. Pluggable, Provider-Agnostic LLM | No `LLMProvider` is invoked at all (research.md decision) — nothing to special-case; grounding/filter-consistency test the provider-agnostic enforcement layer directly. | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | One script, reuses existing modules; disposable Chroma path, no new service, no new dependency. | PASS |
| V. Test & Lint Gates | Harness's own logic gets `pytest` coverage; `eval/run_eval.py` becomes a new CI step alongside `ruff`/`pytest`, satisfying FR-006/SC-004. | PASS |
| VI. Regenerable Derived State | `.cache/eval-chroma` is rebuilt from `eval/golden/fixtures/` every run and is never committed (gitignored) — same disposable-cache contract as the real index. | PASS |

No violations to justify — Complexity Tracking section left empty.

*Re-checked post-Phase 1 (after research.md/data-model.md/contracts/quickstart.md were written):
no changes — the design confirmed every check stays local/deterministic and isolated from real
user data, so all six rows above still hold.*

## Project Structure

### Documentation (this feature)

```text
specs/004-eval-harness/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
eval/
├── run_eval.py               # Entry point: runs one or all checks, prints report, sets exit code
├── golden/
│   ├── grounding.jsonl        # Labeled CandidateReport-shaped fixtures (User Story 1)
│   ├── bullets.jsonl          # Labeled (query -> expected relevant bullet ids) (User Story 2)
│   ├── similar.jsonl          # Labeled (query posting -> expected similar vacancy ids) (US3)
│   ├── filter-consistency.jsonl  # Labeled filter-rule citation examples (User Story 4)
│   └── fixtures/
│       ├── cv/                # Small dedicated CV markdown, ingested only for eval (US2)
│       └── vacancies/         # Small dedicated vacancy folders, ingested only for eval (US3)
└── lib/
    ├── metrics.py             # recall@k, MRR, precision@k, confidence interval (pure functions)
    ├── report.py              # CheckResult/EvalReport dataclasses + markdown rendering
    ├── grounding_check.py     # User Story 1
    ├── retrieval_check.py     # User Story 2
    ├── similar_check.py       # User Story 3
    └── filter_consistency_check.py  # User Story 4

tests/
└── test_eval_metrics.py       # Unit tests for eval/lib/metrics.py and report.py
└── test_eval_checks.py        # Unit tests for each check module against small inline fixtures
```

**Structure Decision**: Single project (matches the existing repo). `eval/` stays a top-level
maintainer tool separate from `src/vacancy_radar/` (already true at scaffold time — see the
constitution's explicit `eval/run_eval.py` reference and the existing `eval/golden/.gitkeep`
placeholder), reusing `vacancy_radar`'s public modules rather than duplicating logic. Each of the
four checks gets its own small module under a new `eval/lib/` package so `run_eval.py` stays a
thin CLI/report-assembly layer, and each check can be unit-tested independently.

## Complexity Tracking

> No violations — this section is intentionally empty; see the Constitution Check table above.
