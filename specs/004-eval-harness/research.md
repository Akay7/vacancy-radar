# Phase 0 Research: Eval Harness

## 1. Should retrieval checks use the real embedding model or a fake?

**Decision**: Use the real `SentenceTransformersEmbedder` (`BAAI/bge-small-en-v1.5`, the same
model production uses), not a fake/mock.

**Rationale**: The entire point of User Story 2 (retrieval recall/MRR) and User Story 3
(similar-vacancy precision) is to catch regressions in the *actual* embedding/retrieval
pipeline a real user gets. `tests/_fakes.py`'s `FakeEmbedder`/`BagOfWordsEmbedder` exist so
`pytest` doesn't need network access or a slow model load for logic tests — but a fake by
construction cannot regress the way a real embedding model can (e.g., a bad model-version bump,
a change in text preprocessing before embedding). The model is already a mandatory local
dependency (Constitution III/IV — no paid API, already installed for ingestion), so using it
here adds no new dependency. SC-001's "under 1 minute" budget is measured with the model already
present in the local cache (e.g., `~/.cache/huggingface`), the same assumption `ruff`/`pytest`
already make about `pip install -e ".[dev]"` having completed first.

**Alternatives considered**: A fake/deterministic embedder (fast, always green) — rejected,
defeats the feature's purpose. A separate smaller/faster embedding model just for eval —
rejected, would validate a different pipeline than the one users actually run (YAGNI).

## 2. What does the grounding/filter-consistency check actually exercise?

**Decision**: Feed curated `CandidateReport`-shaped JSON fixtures directly into
`vacancy_radar.grounding.enforce()` — no retrieval, no embedding model, no LLM, no Chroma
involved in these two checks at all.

**Rationale**: `grounding.enforce()` is a pure function of `(CandidateReport, sources: dict[str,
str])` (see `src/vacancy_radar/grounding.py`). Testing it needs only that shape, not a running
retrieval pipeline. This keeps these two checks near-instant and immune to embedding-model
drift, appropriate since they're validating decision *logic*, not retrieval quality.

**Relationship to `tests/test_grounding.py`**: The existing unit tests are white-box edge-case
tests of `enforce()`'s branches (unknown source id, whitespace/case normalization, the
bracket-prefix bug fix, etc.) and stay as-is — they are not replaced by this feature. The golden
set (`eval/golden/grounding.jsonl`) is a black-box, hand-curated *regression corpus*: a broader,
evolving sample of realistic grounded/fabricated claim pairs (including, going forward, the
exact shape of any real-LLM-discovered failure like the bracket-prefix echo) that a maintainer
can keep growing without touching test code, reported as an aggregate score rather than
individual pytest assertions. The two are complementary, not duplicative.

**Alternatives considered**: Running a real or fake LLM to generate `CandidateReport` objects on
the fly — rejected: reintroduces non-determinism and a live-LLM dependency (violates FR-004) for
a check whose actual target is the enforcement function, not generation quality.

## 3. Where does the eval-only retrieval fixture data live, and how is it isolated?

**Decision**: A small, dedicated CV markdown file and a handful of vacancy folders live under
`eval/golden/fixtures/cv/` and `eval/golden/fixtures/vacancies/`, ingested by the retrieval and
similar-vacancy checks into a disposable Chroma index at `.cache/eval-chroma` (gitignored,
rebuilt every run via the existing `vacancy_radar.ingest` functions, parameterized to a
different `chroma_path` and a different manifest location than production ingestion uses).

**Rationale**: FR-008 requires the harness never read, mutate, or share the maintainer's real
`CV_DIR`/`VACANCY_DIR` or the real `.cache/chroma`. Reusing `data/example/` was considered but
rejected: `data/example/`'s vacancy folders are deliberately messy (some intentionally invalid,
some intentionally natural-key-conflicting) to exercise ingestion-CLI edge cases — repurposing
it as clean, precisely-labeled retrieval ground truth would compromise both purposes. A
dedicated small fixture set lets each labeled example in `bullets.jsonl`/`similar.jsonl`
reference stable, purpose-built ids instead of incidentally-shaped example data.

**Alternatives considered**: Point retrieval checks at whatever the maintainer's `.cache/chroma`
currently holds — rejected: makes the eval non-reproducible (depends on whatever the maintainer
last ingested) and violates the "no dependency on real data" requirement.

## 4. Golden set file format and metrics

**Decision**: JSON Lines (`eval/golden/*.jsonl`), one labeled example per line — matching the
format already implied by the M1-scaffold docstring in `eval/run_eval.py`. Metrics, also as
named in that scaffold docstring:
- Grounding: precision/recall of the enforcement decision (kept-when-should-keep,
  rejected-when-should-reject) as counts + percentage — dataset is small enough that per-fixture
  detail is more useful than a single blended score.
- Bullet retrieval: recall@5 and MRR.
- Similar-vacancy: precision@3.
- Filter-consistency: accuracy reported with sample size and a confidence interval (Wilson score
  interval — closed-form, stdlib `math` only, appropriate for a small-n binomial proportion), not
  a bare percentage that overstates confidence at low n.

**Rationale**: JSONL is trivially hand-editable, diffs cleanly per-line in git, and needs no new
dependency to parse (stdlib `json`, line-by-line). The specific metrics/@k values were already
decided by the maintainer at scaffold time (see `eval/run_eval.py`'s existing docstring) and are
carried forward unchanged rather than re-litigated.

**Alternatives considered**: YAML (rejected — `vacancy.yaml` already uses YAML for
human-authored *source* data; JSONL better signals "generated/structured record," and is the
format the scaffold docstring already committed to). A CSV/table format — rejected, awkward for
the nested candidate-report shape needed by the grounding fixtures.

## 5. Pass/fail thresholds

**Decision**: Grounding and filter-consistency require 100% (any fabricated claim kept, or any
genuine claim wrongly rejected, is a failing run — Principle II is non-negotiable, zero
tolerance). Retrieval recall@5, MRR, and similar-vacancy precision@3 get provisional thresholds
chosen once real fixture data exists and their actual scores are observed, calibrated the same
empirical way `retriever.py`'s `MIN_SIMILARITY = 0.6` was calibrated against real model output
(see `specs/002-similar-retrieval/research.md`) — not picked a priori in this document.

**Rationale**: Spec Assumptions already defer exact retrieval thresholds to implementation-time
calibration; committing to a specific number here without real fixture scores to check it
against would be guessing.

## 6. CI integration

**Decision**: Add `eval/run_eval.py` as a step in `.github/workflows/ci.yml`, after `ruff check
.` and `pytest`, failing the job (non-zero exit) when any check's aggregate score is below its
threshold.

**Rationale**: FR-006 and SC-004 explicitly require the harness to function as an automated
gate, not a manual-only tool — and Constitution V already treats `ruff`+`pytest` as pass/fail
gates for "done," so adding this check to the same job is the natural, YAGNI-compliant home
for it (no new CI infrastructure).

**Alternatives considered**: Manual-only validation (like `/analyze`'s `quickstart.md`, which
intentionally needs a real, non-deterministic LLM and so can't be a CI gate) — rejected here
because, per research item 1-3 above, every one of this feature's four checks *is* fully
deterministic and local, so there's no reason to leave it manual.

## 7. Report format

**Decision**: `eval/run_eval.py` prints a markdown table to stdout (per-check status, aggregate
metric(s), pass/fail) and exits non-zero if any check fails — matching the scaffold docstring's
"writes the results as a markdown table for the README." No separate report file is written
automatically; a maintainer updating the README's own eval numbers copies the printed table by
hand.

**Rationale**: Keeps the script simple (YAGNI) — auto-writing to a committed file would add a
generated-file-freshness problem (is the committed report stale relative to the current
fixtures/code?) that this feature doesn't need to solve.
