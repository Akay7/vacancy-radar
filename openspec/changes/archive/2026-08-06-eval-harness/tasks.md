## 1. Fixture content prerequisites

- [x] 1.1 Write a test asserting `tests/fixtures/generate.py`'s
      `write_search_fixtures` emits a deterministic multi-result pair:
      two documents, in two different vacancies, sharing a distinctive
      multi-word phrase neither shares with any other fixture document.
- [x] 1.2 Extend `write_search_fixtures` with that multi-result pair
      (new constants alongside `DISTINCTIVE_PROPER_NOUN`/
      `RARE_TECH_TERM`, following the existing fixed-content pattern —
      never drawn from `rng`).
- [x] 1.3 Regenerate the committed fixture tree
      (`uv run python tests/fixtures/generate.py`) and confirm the diff
      only adds the new multi-result documents, touching no existing
      committed file.
- [x] 1.4 Run the existing `tests/fixtures/test_generate.py` and
      `tests/index/test_search.py` suites to confirm the regenerated
      tree doesn't break any stage 4 assertion.

## 2. eval/metrics.py

- [x] 2.1 Write `tests/eval/test_metrics.py` covering every scenario in
      `specs/eval-metrics/spec.md`: single-hit recall, absent-hit
      recall, 2/3 partial recall, MRR at rank 3, MRR with no hit, empty-
      retrieval handling for both metrics, empty-expectation handling
      for both metrics, and multi-expected-document MRR.
- [x] 2.2 Implement `eval/__init__.py` (empty package marker) and
      `eval/metrics.py`: `recall_at_k(expected, retrieved, k) -> float`
      and `mrr(expected, retrieved) -> float`, per design.md's empty-
      expectation and empty-retrieval rules.
- [x] 2.3 Run `uv run pytest tests/eval/test_metrics.py` green.

## 3. eval/queries.yaml

- [x] 3.1 Write `tests/eval/test_queries.py` covering every scenario in
      `specs/eval-queries/spec.md`: record shape and count, per-category
      target counts, id uniqueness, every `expected_doc_ids` entry
      resolving in the fixture index, `filtered`-category `filter`
      mappings using only valid keys, and paraphrase queries sharing no
      content word (stopwords excluded) with their target document(s).
- [x] 3.2 Author `eval/queries.yaml`: 30 records across the seven
      categories (`exact_name` 5, `technical` 5, `paraphrase` 4,
      `temporal` 4, `multi_result` 4, `filtered` 4, `negative` 4),
      written against `tests/fixtures/vault` content only — reusing
      `search-fixtures-corp`'s paraphrase and rare-term documents, the
      new multi-result pair from section 1, and the generated
      companies/roles/dates/tags/statuses for the rest. No real company
      names, no tuning a query's wording after seeing it score poorly.
- [x] 3.3 Run `uv run pytest tests/eval/test_queries.py` green,
      including against a fixture index built from the regenerated
      vault.

## 4. eval/run.py and EvalReport

- [x] 4.1 Write `tests/eval/test_run.py` covering
      `specs/eval-runner/spec.md`'s sweep, determinism, per-category-
      sums-to-overall, and `to_markdown` scenarios, using a small
      hand-picked `configs` subset (not the full 12-combination sweep)
      wherever a scenario doesn't specifically need the full sweep.
- [x] 4.2 Implement `EvalConfig` (frozen dataclass: `mode`,
      `vector_weight: float | None`, `fusion_strategy: FusionStrategy |
      None`) and the `FULL_SWEEP` constant (12 combinations) in
      `eval/run.py`.
- [x] 4.3 Implement the `_fusion_strategy_env` context manager
      (set/restore `SEARCH_FUSION_STRATEGY`) and `run_eval(queries,
      index, configs) -> EvalReport`, calling `search(index,
      query.query, mode=..., vector_weight=..., limit=5, **unpacked
      filter)` per query per config.
- [x] 4.4 Implement `EvalReport`: per-`(config, category)` rows, the
      derived overall-per-config rollup, and `to_markdown()`.
- [x] 4.5 Run `uv run pytest tests/eval/test_run.py` green.

## 5. Findings tests against the fixture corpus

- [x] 5.1 Write `tests/eval/test_findings.py` with the three directional
      assertions from `specs/eval-runner/spec.md`: exact_name recall
      keyword ≥ semantic, paraphrase recall semantic > keyword, and
      hybrid-at-chosen-weight overall recall@5 ≥ the better single mode
      — running `run_eval` against the fixture index with `FULL_SWEEP`
      (or the minimal subset each assertion needs).
- [x] 5.2 Run the findings suite and record the actual numbers (overall
      and per-category recall@5/MRR for every swept combination) for
      use in sections 6 and 7. If any of the three directional findings
      fails, record that plainly instead of adjusting the query set to
      make it pass.

      **Recorded numbers** (full sweep, 30 queries, fixture vault):
      keyword overall recall@5=0.761/MRR=0.675; semantic
      overall=0.678/0.583; hybrid+RRF overall=0.672/0.541 (identical
      across all 5 weights - *underperforms* both single modes);
      hybrid+LinearCombination overall=0.794/0.687 at weights
      0.3-0.6 (identical across those four, 0.7 ties on recall but
      drops to MRR=0.636). Per-category: exact_name keyword=1.000 vs
      semantic=0.800 (keyword wins, as hypothesized); paraphrase
      semantic=0.750 vs keyword=0.250 (semantic strictly wins, as
      hypothesized); multi_result and temporal are weak everywhere
      (recall 0.25-0.42 and keyword=1.000/semantic=0.250
      respectively). All three directional findings hold. **This
      contradicts stage 4's hypothesis on two points**: RRF (the
      stage-4 default fusion) underperforms plain keyword search on
      this corpus, and Linear Combination beats it - and the
      previous default_vector_weight (0.7) is not the winner; 0.3-0.6
      tie for best, with 0.7 slightly worse on MRR.

## 6. Private CLI entry point

- [x] 6.1 Write a `tests/test_cli.py` addition asserting `_eval` is
      absent from `vacancy-radar --help`'s listed commands, and that
      invoking `vacancy-radar _eval` exits successfully and prints a
      markdown table to stdout (mark it with the existing `embedding`
      marker; keep it fast by building the index once for the test).
- [x] 6.2 Implement the hidden `_eval` command in `cli.py`: insert the
      repo root onto `sys.path`, import `eval.run`, build a temporary
      index from `tests/fixtures/vault`, run `FULL_SWEEP` via
      `run_eval`, and `typer.echo` the report's `to_markdown()` output.
- [x] 6.3 Run `uv run pytest tests/test_cli.py` green.

## 7. config.py amendment

- [x] 7.1 From section 5's recorded numbers, choose the winning
      `vector_weight`/`fusion_strategy` for `SearchConfig`'s defaults.
      **Chosen: `default_vector_weight=0.5`,
      `fusion_strategy=LINEAR_COMBINATION`** (0.3-0.6 tied on recall@5;
      0.5 is the middle of that tied band; 0.7 ties on recall but is
      lower on MRR).
- [x] 7.2 Write a test confirming `SearchConfig()`'s
      `default_vector_weight` and `fusion_strategy` equal the chosen
      values (a regression guard, alongside the existing
      `test_search_config_default_mode_is_a_valid_search_mode`-style
      checks in `tests/index/test_search.py`).
- [x] 7.3 Update `SearchConfig`'s field defaults in `config.py` to the
      chosen values; if they contradict stage 4's keyword-favoring
      hypothesis for this corpus, note that in the docstring alongside
      the existing default-value comments. Also updated three
      pre-existing stage-4 tests (`tests/test_config.py`'s documented-
      defaults test; `tests/index/test_search.py`'s
      `test_dual_path_hit_outranks_single_path_hit` and
      `test_effective_vector_weight_is_none_under_default_rrf_fusion`)
      that implicitly relied on RRF being the default fusion strategy -
      they now request RRF explicitly via `SEARCH_FUSION_STRATEGY`,
      matching the pattern the adjacent Linear Combination test already
      used. No change to `search.py` itself.
- [x] 7.4 Run `uv run pytest tests/index/test_search.py
      tests/test_config.py` green.

## 8. README amendment

- [x] 8.1 Fill in `README.md`'s retrieval evaluation table (currently a
      stub) with the per-category recall@5/MRR breakdown for the chosen
      config, plus keyword-only and semantic-only rows for comparison.
- [x] 8.2 Add the paragraph explaining what the numbers show: which
      category favors which mode, why the chosen weight/fusion was
      selected, and — if applicable — where a directional finding
      contradicted the stage-4 hypothesis.
- [x] 8.3 Add the synthetic-fixture limitation note: these numbers
      characterize the retrieval design against generated fixtures, not
      a real vault: a second eval run after a real import belongs at
      stage 9.
- [x] 8.4 Note the reranker/score-floor future-work items (not built in
      this change) in the README's evaluation section.

## 9. Final verification

- [x] 9.1 Run `uv run pytest` (full suite) green. 286 passed.
- [x] 9.2 Run `uv run ruff check .` and `uv run ruff format --check .`
      green — no `print()` calls anywhere under `eval/`. Also ran
      `uv run pre-commit run --all-files` (all hooks pass, including
      `check-yaml` on `eval/queries.yaml`).
- [x] 9.3 Confirm no changes were made to `src/vacancy_radar/index/
      search.py` (`git diff --stat` against the base branch). Confirmed
      empty diff.
- [x] 9.4 Confirm a fresh `uv sync --all-groups` plus `uv run pytest`
      succeeds with network access limited to the cached embedding
      model (matches CI's `actions/cache` step). `pyproject.toml`/
      `uv.lock` are unchanged (no new dependency, runtime or dev); the
      embedding model is already present in the local Hugging Face
      cache CI's `actions/cache` step targets.
