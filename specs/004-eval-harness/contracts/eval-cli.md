# CLI Contract: `eval/run_eval.py`

This feature is a standalone script (not a `vacancy-radar` subcommand — it's a maintainer tool,
not a shipped end-user feature; see plan.md's Project Structure decision). The contract surface
is this one script's invocation, arguments, exit codes, and stdout shape.

## `python eval/run_eval.py`

**Purpose**: Run all four checks (grounding, bullet retrieval, similar-vacancy, filter-
consistency) against `eval/golden/`, print a combined markdown report, and set an exit code
suitable for CI gating.

**Args**: none required. Optional `--check {grounding,bullets,similar,filter-consistency}`
(repeatable) restricts the run to one or more specific checks (FR-002) — omitted means "all
four."

**Behavior**:
- Ingests `eval/golden/fixtures/cv/` and `eval/golden/fixtures/vacancies/` into a disposable
  `.cache/eval-chroma` index before running the bullet-retrieval and similar-vacancy checks
  (rebuilt every run — never reuses a stale index, never touches the real `.cache/chroma`).
- The grounding and filter-consistency checks need no ingestion step — they call
  `grounding.enforce()` directly per fixture.
- Never calls an `LLMProvider` or makes a network request.
- Never reads `CV_DIR`/`VACANCY_DIR` env vars or the maintainer's real data.

**Exit codes**: `0` when every requested check's `status` is `"pass"` or `"skipped"`. Non-zero
when any requested check's `status` is `"fail"` — either a metric fell below its threshold, or a
labeled fixture's expected outcome didn't match (FR-006). A fixture/data error (FR-007) also
causes a non-zero exit (it means the golden set itself is broken and needs a maintainer's
attention), but is reported distinctly from a quality regression in the printed report.

**Stdout contract**: A markdown report — one table per check (or one combined table with a
per-check row, decided in tasks phase) showing: check name, status, sample size, aggregate
metric(s), and a listing of any failing fixture ids with their reason and `kind`
(`regression`/`fixture_error`). Suitable to copy-paste into the README by hand (per the
scaffold's own docstring intent) — this script does not write any file itself.

**Idempotency**: Running twice with no changes to `eval/golden/` or the relevant `src/`
code produces an identical report and exit code (all four checks are deterministic — no live
LLM, no randomness).

## Cross-cutting

- This script is added as a CI step in `.github/workflows/ci.yml`, after `ruff check .` and
  `pytest`, so a failing eval run fails the same CI job those already gate (research.md item 6).
- `eval/golden/fixtures/` and `.cache/eval-chroma` are never read by, or shared with, any code
  path under `src/vacancy_radar/` outside of this script's own invocation of `ingest`/`retriever`
  functions with explicit, eval-specific paths passed in — production code never points at
  `eval/` and this script never points at `data/user/` or `.cache/chroma`.
