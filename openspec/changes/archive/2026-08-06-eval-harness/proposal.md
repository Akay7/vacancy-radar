## Why

Stage 4 shipped hybrid search with a fusion strategy and a
`default_vector_weight` chosen by hypothesis (a proper-noun-heavy corpus
should favor keyword), not by measurement. Every later stage — the
public `eval` command, the CLI, the MCP server — will be built on top of
whatever retrieval configuration is shipped, and none of them can
retune it from data after the fact without risking that a bad weighting
gets masked by snippet length or result-limit choices made in those
later layers. This stage measures recall and MRR across modes, weights,
and fusion strategies against a labelled query set, and sets
`default_vector_weight` and `fusion_strategy` to whatever the numbers
actually support — reporting the result plainly even if it contradicts
the stage-4 hypothesis.

## What Changes

- Add `eval/queries.yaml`: 30 labelled queries against committed fixture
  `doc_id`s, spanning `exact_name`, `technical`, `paraphrase`,
  `temporal`, `multi_result`, `filtered`, and `negative` categories.
- Add `eval/metrics.py`: `recall_at_k` and `mrr`, both handling multiple
  expected documents and empty expectations.
- Add `eval/run.py`: `run_eval` sweeps keyword, semantic, and hybrid
  (at vector_weight 0.3/0.4/0.5/0.6/0.7, under both RRF and Linear
  Combination fusion) and returns an `EvalReport` with overall and
  per-category recall@5 and MRR, rendered as a markdown table.
- Add a private `vacancy-radar _eval` CLI entry point that runs the
  sweep against the fixture index and prints the rendered report — a
  placeholder replaced by the public `eval` command at stage 6.
- Amend `config.py`'s `SearchConfig` field defaults
  (`default_vector_weight`, `fusion_strategy`) to the measured winner,
  justified by the recall/MRR numbers this stage produces.
- Fill in `README.md`'s retrieval evaluation table (left empty at stage
  0) with the per-category breakdown and a paragraph on what the
  numbers show, including the synthetic-fixture limitation.

No CLI commands beyond the private runner, no MCP surface, no writes to
the vault or index, and no changes to `search.py`'s retrieval behavior —
a retrieval bug found here is a separate change, not a fix folded into
this one.

## Capabilities

### New Capabilities
- `eval-metrics`: pure recall@k and MRR functions over expected vs.
  retrieved document ids, handling ties, multiple expected documents,
  and empty expectations.
- `eval-queries`: the committed labelled query set (`eval/queries.yaml`)
  and the integrity guarantees that keep it trustworthy — every
  `expected_doc_id` resolves in the fixture index, every category meets
  its target count, no duplicate ids, paraphrase queries verified
  content-word-free against their target.
- `eval-runner`: `run_eval`'s sweep across mode/weight/fusion
  combinations, `EvalReport`'s markdown rendering, the private
  `vacancy-radar _eval` entry point, and the directional findings
  (exact_name favors keyword, paraphrase favors semantic, hybrid at the
  chosen weight matches or beats the better single mode) the project
  asserts about its own retrieval design.

### Modified Capabilities
(none — `SearchConfig`'s documented behavior is "each field holds a
concrete default value"; this change updates which concrete values
those are, not the requirement itself. The chosen values and the
measurements behind them are recorded in this change's design.md and in
the README, not as a spec requirement change.)

## Impact

- New `eval/` package: `eval/queries.yaml`, `eval/metrics.py`,
  `eval/run.py`, `eval/__init__.py`.
- `src/vacancy_radar/cli.py`: one new private, hidden subcommand
  (`_eval`) delegating to `eval.run.run_eval`.
- `src/vacancy_radar/config.py`: `SearchConfig.default_vector_weight`
  and `SearchConfig.fusion_strategy` field defaults change to the
  measured winner. No signature or field changes.
- `README.md`: retrieval evaluation table and surrounding paragraph
  filled in.
- Test-only additions to `pyproject.toml`'s dev dependency group, if a
  YAML-parsing or test-fixture dependency is needed beyond what's
  already there (`ruamel.yaml` is already a runtime dependency and can
  likely be reused — see design.md).
- No changes to `src/vacancy_radar/index/search.py` or any other
  retrieval code path's behavior.
