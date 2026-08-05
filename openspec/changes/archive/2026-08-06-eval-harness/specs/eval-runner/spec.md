## ADDED Requirements

### Requirement: run_eval sweeps every mode/weight/fusion combination and produces one result row per combination
`run_eval(queries, index, configs)` SHALL, for each `EvalConfig` in
`configs`, run every query in `queries` against `index` and produce
exactly one result row per `(mode, vector_weight, fusion_strategy)`
combination in `configs`, per category present in `queries`, plus one
overall row for that combination.

#### Scenario: the full sweep produces one row per combination
- **GIVEN** `run_eval` called with the full 12-combination sweep
  (`keyword`; `semantic`; `hybrid` at vector_weight 0.3/0.4/0.5/0.6/0.7
  under RRF and under Linear Combination fusion)
- **WHEN** the resulting `EvalReport` is inspected
- **THEN** it contains an overall row for each of the 12 combinations
- **THEN** it contains a per-category row for each combination and each
  category present in `queries`

### Requirement: Keyword mode's rows are identical across every swept vector_weight
`run_eval`'s keyword-mode rows SHALL report the same `recall_at_5` and
`mrr` values regardless of which `vector_weight` value the swept
`EvalConfig` carries, since keyword mode never reads `vector_weight`.

#### Scenario: keyword rows do not vary with vector_weight
- **GIVEN** `run_eval` called with `configs` containing keyword-mode
  entries at two different `vector_weight` values
- **WHEN** those two rows' `recall_at_5` and `mrr` are compared
- **THEN** they are equal

### Requirement: Semantic mode's rows are identical across every swept vector_weight
`run_eval`'s semantic-mode rows SHALL report the same `recall_at_5` and
`mrr` values regardless of which `vector_weight` value the swept
`EvalConfig` carries, since semantic mode never reads `vector_weight`.

#### Scenario: semantic rows do not vary with vector_weight
- **GIVEN** `run_eval` called with `configs` containing semantic-mode
  entries at two different `vector_weight` values
- **WHEN** those two rows' `recall_at_5` and `mrr` are compared
- **THEN** they are equal

### Requirement: run_eval's results are deterministic across runs
`run_eval` SHALL produce `EvalReport`s with identical rows in identical
order when called twice with identical `queries`, `index`, and
`configs`.

#### Scenario: repeating run_eval reproduces the same report
- **GIVEN** the same `queries`, `index`, and `configs`
- **WHEN** `run_eval` is called twice
- **THEN** the two resulting `EvalReport`s have identical rows in
  identical order

### Requirement: Per-category rows sum consistently with the overall row
A swept combination's overall `recall_at_5` (and `mrr`) row SHALL equal
the query-count-weighted mean of that combination's per-category
`recall_at_5` (and `mrr`) values, within floating-point tolerance.

#### Scenario: category rows reconcile with the overall row
- **GIVEN** one swept combination's per-category rows and its overall
  row from an `EvalReport`
- **WHEN** the per-category `recall_at_5` values are combined as a
  query-count-weighted mean
- **THEN** the result equals that combination's overall `recall_at_5`,
  within floating-point tolerance
- **THEN** the same holds for `mrr`

### Requirement: exact_name recall is at least as high under keyword as under semantic
`exact_name`-category `recall_at_5` SHALL be at least as high under the
keyword-mode row as under the semantic-mode row, across the query set.

#### Scenario: keyword does not lose ground on exact_name recall
- **GIVEN** an `EvalReport` covering both keyword-mode and semantic-mode
  configs
- **WHEN** each mode's `exact_name` per-category `recall_at_5` is
  compared
- **THEN** the keyword-mode value is greater than or equal to the
  semantic-mode value

### Requirement: paraphrase recall is strictly higher under semantic than under keyword
`paraphrase`-category `recall_at_5` SHALL be strictly higher under the
semantic-mode row than under the keyword-mode row, across the query
set.

#### Scenario: semantic strictly outperforms keyword on paraphrase recall
- **GIVEN** an `EvalReport` covering both keyword-mode and semantic-mode
  configs
- **WHEN** each mode's `paraphrase` per-category `recall_at_5` is
  compared
- **THEN** the semantic-mode value is strictly greater than the
  keyword-mode value

### Requirement: Hybrid at the chosen weight is at least as good as the better single mode overall
The hybrid config's overall `recall_at_5` SHALL, at the chosen
(measured-winner) `vector_weight` and `fusion_strategy`, be greater
than or equal to the higher of keyword-mode's and semantic-mode's
overall `recall_at_5`.

#### Scenario: the chosen hybrid config does not underperform both single modes
- **GIVEN** an `EvalReport` covering keyword mode, semantic mode, and
  hybrid mode at the chosen `vector_weight`/`fusion_strategy`
- **WHEN** the hybrid config's overall `recall_at_5` is compared to the
  higher of keyword's and semantic's overall `recall_at_5`
- **THEN** the hybrid value is greater than or equal to it

### Requirement: EvalReport renders as a markdown table
`EvalReport` SHALL provide a method that renders its rows as a markdown
table suitable for pasting into `README.md`, including per-category
columns or sections, not only the overall figures.

#### Scenario: to_markdown produces a well-formed table
- **GIVEN** a populated `EvalReport`
- **WHEN** its markdown-rendering method is called
- **THEN** the result is a string containing a markdown table header row
  and at least one data row per swept combination
- **THEN** the per-category breakdown is present in the output, not only
  overall figures

### Requirement: A private, hidden vacancy-radar _eval command runs the full sweep
The CLI SHALL expose a `vacancy-radar _eval` command, marked hidden
(not shown in `--help`), that builds an index from
`tests/fixtures/vault`, runs the full sweep via `run_eval`, and prints
the resulting `EvalReport`'s markdown rendering to stdout without using
`print()`.

#### Scenario: _eval is absent from --help output
- **GIVEN** the CLI's top-level `--help` output
- **WHEN** its listed commands are inspected
- **THEN** `_eval` does not appear among them

#### Scenario: _eval runs the full sweep and prints a markdown report
- **GIVEN** a checkout with the committed fixture vault present
- **WHEN** `vacancy-radar _eval` is invoked
- **THEN** it exits successfully
- **THEN** its stdout contains a markdown table produced by
  `EvalReport.to_markdown()`

### Requirement: The eval suite runs in a fresh clone with no network access beyond the cached embedding model
`run_eval`'s full sweep, and its test suite, SHALL complete against a
fresh clone of the repository using only the embedding model already
cached locally (or in CI's model cache) — no other network access.

#### Scenario: the eval test suite requires no network beyond the cached model
- **GIVEN** a fresh clone with dependencies installed and the embedding
  model already present in the local cache
- **WHEN** the eval test suite is run with network access disabled
  beyond that cache
- **THEN** it completes without a network-dependent failure
