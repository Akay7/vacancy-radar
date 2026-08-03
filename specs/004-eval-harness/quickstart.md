# Quickstart: Eval Harness

Validates the feature end-to-end. Unlike `/analyze`'s quickstart ([[003-analyze-report-generation]]),
every scenario here is fully local and deterministic — no LLM backend, no network, no `.env`
configuration needed.

## Prerequisites

- Dependencies installed: `pip install -e ".[dev]"` (same as `ruff`/`pytest`).
- The local embedding model available (first run downloads/caches `BAAI/bge-small-en-v1.5`, same
  as `vacancy-radar ingest` already requires).
- No `CV_DIR`/`VACANCY_DIR`/`.env` setup needed — this script never touches real user data.

## Scenario 1 — Full suite, all green (User Stories 1-4)

```bash
python eval/run_eval.py
```

**Expected**: exit code `0`; a markdown report with four rows (grounding, bullet retrieval,
similar-vacancy, filter-consistency), each `status: pass`, printed in well under a minute.

## Scenario 2 — Grounding check catches a real regression (User Story 1 / SC-003)

Temporarily break `grounding.enforce()`'s verbatim check (e.g., make `_is_grounded` always
return `True`), then re-run:

```bash
python eval/run_eval.py --check grounding
```

**Expected**: exit code non-zero; the grounding row reports `status: fail`, and the fixtures
whose `expect_grounded: false` fabricated claims are labeled as regressions (`kind: regression`)
in the printed failure list. Revert the change afterward.

## Scenario 3 — Running a single check (FR-002)

```bash
python eval/run_eval.py --check bullets
```

**Expected**: only the bullet-retrieval check runs (recall@5, MRR reported); the report does not
mention the other three checks; runs noticeably faster than the full suite.

## Scenario 4 — Missing golden file is reported, not crashed (edge case)

```bash
mv eval/golden/similar.jsonl /tmp/similar.jsonl.bak
python eval/run_eval.py
```

**Expected**: exit code `0` overall if the other three checks still pass; the similar-vacancy row
reports `status: skipped`, not a stack trace and not silently omitted from the report. Restore
the file afterward: `mv /tmp/similar.jsonl.bak eval/golden/similar.jsonl`.

## Scenario 5 — Fixture/data error reported distinctly from a real miss (FR-007)

Temporarily edit one line of `eval/golden/bullets.jsonl` so `expected_bullet_ids` references an
id that doesn't exist among the eval fixture CV's ingested bullets (e.g. `"bullet-999"`), then:

```bash
python eval/run_eval.py --check bullets
```

**Expected**: that fixture is reported with `kind: fixture_error` (not `kind: regression`) and a
reason naming the missing bullet id — a maintainer reading the report can immediately tell this
is a broken fixture, not a retrieval-quality problem. Revert the edit afterward.

## Scenario 6 — Isolation from real data (FR-008)

```bash
vacancy-radar ingest   # populates the real .cache/chroma from data/example/
python eval/run_eval.py
ls .cache/   # both chroma/ (real) and eval-chroma/ (eval-only) present, untouched by each other
```

**Expected**: the eval run's results are identical whether or not `vacancy-radar ingest` was run
first — it never reads `.cache/chroma`, and running it does not modify or delete `.cache/chroma`.

## Scenario 7 — CI gate (SC-004)

```bash
ruff check . && pytest && python eval/run_eval.py
```

**Expected**: all three commands run in sequence exactly as `.github/workflows/ci.yml` will
invoke them; the combined exit code is non-zero if any one of the three fails — matches the
existing `ruff`/`pytest` gate behavior, now with the eval suite included.
