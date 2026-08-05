## Context

Stage 4 (`retrieval`) shipped `search()` with three modes, a swappable
fusion strategy (`SearchConfig.fusion_strategy`, RRF by default), and a
`default_vector_weight` of `0.7` — chosen as a plausible starting point,
not measured. `SearchConfig` and `resolve_search_config()` already exist
specifically so this stage could retune those two defaults without
touching `search.py` (see stage 4's design.md). This stage builds the
measurement that makes that retuning defensible: a labelled query set
against the committed fixture vault, `recall@5`/`MRR` metrics, a sweep
runner across every (mode, vector_weight, fusion_strategy) combination
worth comparing, and the resulting `config.py` change.

Two things this stage needs that stage 4 didn't provide a seam for:

1. **A way to select `fusion_strategy` per call.** `search()` exposes
   `mode` and `vector_weight` as explicit call arguments, but not
   `fusion_strategy` — that's read once, inside `search()`, from
   `resolve_search_config()`, which in turn reads the
   `SEARCH_FUSION_STRATEGY` environment variable. The sweep runner has
   no `search.py` code change available to it (constraint: do not
   modify `search.py`'s behavior), so it drives fusion strategy the only
   way `search()` exposes: setting `SEARCH_FUSION_STRATEGY` in the
   environment before each hybrid call.
2. **A labelled query set against fixture content.** Stage 4's search
   tests each assert one behavior against one hand-built fixture
   document. This stage needs a broader, categorized set — 30 queries,
   each with known-correct `expected_doc_ids` — reusing the
   `search-fixtures-corp` paraphrase/rare-term documents stage 4 already
   added to `tests/fixtures/generate.py`, extended with additional
   fixture content where a category (e.g. `multi_result`, `temporal`)
   needs documents stage 4 didn't create.

## Goals / Non-Goals

**Goals:**
- Measure recall@5 and MRR, overall and per category, across keyword,
  semantic, and hybrid (5 weights × 2 fusion strategies) against the
  committed fixture vault.
- Make the per-category breakdown, not just the aggregate, the thing
  `EvalReport` renders — an aggregate number can't show that a weighting
  which wins overall destroys `paraphrase` recall.
- Set `SearchConfig`'s `default_vector_weight` and `fusion_strategy`
  field defaults to whatever the sweep actually supports, and say so
  plainly in the README even if it contradicts stage 4's keyword-favoring
  hypothesis.
- A private `vacancy-radar _eval` entry point a developer can run
  locally to reproduce the sweep and its report.

**Non-Goals:**
- A public `eval` CLI command (stage 6) or an MCP tool.
- Any change to `search.py`'s retrieval behavior, ranking, or fusion
  math — a bug found here is reported, not fixed, in this change.
- A reranker or query expansion, even if the numbers suggest one would
  help (recorded as README future work instead).
- Evaluation against a real vault — the fixture corpus is synthetic;
  see Risks.
- A score floor for low-relevance results — see the Decisions entry
  below on negative-category scoring.

## Decisions

**`queries.yaml` is a flat list of records, parsed with `ruamel.yaml`
(already a runtime dependency — no new dependency needed).** Each
record: `id` (str, unique), `query` (str), `expected_doc_ids` (list of
str, possibly empty — only for `negative`), `category` (one of the
seven documented category strings), `note` (str, free-text rationale),
and an optional `filter` mapping (only present on `filtered`-category
queries) whose keys mirror `search()`'s filter parameters
(`company_slug`, `status`, `kind`, `tags`, `since`) so the runner can
unpack it directly into the corresponding `search()` call arguments.
Loaded once per `run_eval` invocation into a list of frozen `Query`
dataclasses — no ORM, no schema-validation library, since a handful of
flat fields and the integrity tests already cover correctness.

**`recall_at_k` and `mrr` treat an empty `expected` as trivially
satisfied (score `1.0`), independent of what was retrieved.** This is
what lets `negative`-category queries (`expected_doc_ids: []`) score
`1.0` "when nothing relevant is returned" per the spec — but note the
metric is trivially `1.0` regardless of what *is* returned, because
recall and MRR are both defined over "fraction/rank of expected items
found," and there's nothing to find. Neither metric penalizes a
negative query for returning irrelevant results — that's a precision
question, out of scope here (see the negative-category decision below).
`recall_at_k([], anything, k)` and `mrr([], anything)` both return `1.0`
by this same rule, verified by the metrics test suite's "empty
expectations" scenarios.

**Both metrics are computed over the same top-5 retrieved window, not a
separately-sized window per metric.** `run_eval` calls `search(...,
limit=5)` once per (query, config) pair and feeds the resulting doc-id
list to both `recall_at_k(expected, retrieved, k=5)` and
`mrr(expected, retrieved)`. An alternative — fetching a deeper window
(e.g. `limit=20`) so MRR can find a hit recall@5 already missed — was
rejected: it would let MRR report a rank recall@5 says doesn't exist in
the window that matters for this product (a five-result MCP tool
response), producing two metrics answering two different questions
under one report. Keeping both metrics scoped to the same top-5 window
means every number in `EvalReport` describes the same thing: "how good
are the first five results."

**Fusion strategy is swept via the `SEARCH_FUSION_STRATEGY` environment
variable, set and restored around each hybrid call.** A small context
manager (`_fusion_strategy_env(strategy)`) sets
`os.environ["SEARCH_FUSION_STRATEGY"]` on entry and restores its prior
value (or deletes it) on exit — the only override seam `search()`
exposes for this field (see Context). `mode` and `vector_weight` are
passed as ordinary explicit `search()` arguments, since those already
have call-level parameters. Keyword and semantic configs never touch
this environment variable at all, which is also *why* their rows come
out identical across the swept weights and fusion strategies: those two
modes' code paths in `search.py` never read `vector_weight` or
`fusion_strategy` to begin with — the sweep isn't specially short-
circuiting them, `search()`'s existing behavior already does that.

**`run_eval(queries, index, configs)` takes an explicit `configs`
sequence rather than always running the full sweep internally.** The
full 12-combination sweep (`keyword`; `semantic`; `hybrid` × 5 weights ×
2 fusion strategies) is exposed as a module-level constant
(`FULL_SWEEP`) that the private CLI command passes by default; tests
that only need to check one property (e.g. "keyword rows are identical
across weights") pass a narrower `configs` list so they don't pay for
the full sweep's ~360 `search()` calls just to assert one thing.
`EvalConfig` is a frozen dataclass: `mode: SearchMode`, `vector_weight:
float | None`, `fusion_strategy: FusionStrategy | None` — the latter two
are `None` and ignored for `keyword`/`semantic` configs, mirroring
`SearchResults.effective_vector_weight`'s own `None`-when-inapplicable
convention from stage 4.

**`EvalReport` holds per-`(config, category)` rows plus a derived
overall-per-`config` rollup, and renders one markdown table.** Each row:
`mode`, `vector_weight`, `fusion_strategy`, `category` (or `"overall"`),
`recall_at_5`, `mrr`, `n_queries`. The overall row per config is a
query-count-weighted mean of that config's per-category rows, which is
what makes "per-category breakdown sums consistently with the overall
figure" a checkable invariant rather than a documentation claim.
`to_markdown()` renders the full table (used by the private CLI's
stdout output and copyable directly into the README); the README's own
copy is a curated excerpt (the winning config's per-category rows plus
the cross-config overall comparison), assembled by hand from a `_eval`
run, not regenerated by CI on every commit — consistent with this being
a one-time (per stage) measurement, not a live dashboard.

**The private entry point lives at `vacancy-radar _eval`, `hidden=True`
in Typer, and imports `eval/` from the repo checkout, not from the
installed package.** `eval/` is a top-level directory (`eval/queries.yaml`,
`eval/metrics.py`, `eval/run.py`, `eval/__init__.py`) sibling to `src/`
and `tests/`, matching the deliverable's specified paths and mirroring
how `tests/fixtures/generate.py` already lives outside the installed
`vacancy_radar` package. `pyproject.toml`'s wheel target only packages
`src/vacancy_radar` (unchanged by this stage), so `eval/` is never
shipped — this command is a development tool, replaced outright by the
public `eval` command at stage 6, not a stage-5 feature meant to survive
in a built wheel. Because a console-script entry point's `sys.path`
doesn't include the repo root by default, `cli.py`'s `_eval` command body
inserts the repo root (derived from `Path(__file__)`, same pattern
`tests/index/test_search.py` already uses for `tests/fixtures/`) before
importing `eval.run`, so `uv run vacancy-radar _eval` works from a plain
checkout without editable-install path tricks. The command builds a
temporary index from `tests/fixtures/vault/` (via `build_index`, exactly
as `tests/index/test_search.py`'s `fixture_index` fixture does) into a
`tempfile.TemporaryDirectory`, runs `FULL_SWEEP`, and echoes
`report.to_markdown()` via `typer.echo` — never `print()` (T20).

**`recall@5` is the headline metric because it matches the product this
retrieval serves: an MCP tool call or CLI search returns a handful of
results (`SearchConfig.default_limit` is `10`; this eval measures the
tighter `5` since that's the number a client is likeliest to actually
look at), and the operative question is "is the right document
somewhere in that handful," not "what's the exact best achievable rank."
**MRR adds rank sensitivity within that handful** — two configs can tie
on recall@5 (both found the target in the top 5) while one consistently
ranks it 1st and the other 5th; MRR distinguishes them, which matters
for choosing a fusion strategy where multiple candidates clear recall@5
but users still notice which one is a literal first result.

**Per-category reporting is mandatory, not a nice-to-have, because this
corpus is proper-noun-heavy by design (stage 4's fixtures) and an
aggregate number would hide the exact trade-off this stage exists to
surface.** A vector_weight that wins on the aggregate could be winning
by improving `technical` and `multi_result` recall while quietly
destroying `paraphrase` recall (the one category keyword mode
structurally cannot serve at all) — the aggregate wouldn't show that
because `paraphrase` is a minority of 30 queries. The per-category rows
are what let the "exact_name recall is at least as high under keyword
as under semantic" and "paraphrase recall is strictly higher under
semantic than under keyword" findings be checked directly, rather than
inferred from a single blended number.

**Negative-category queries are scored as trivially-satisfied recall,
not enforced to return zero results — a score floor is explicitly out
of scope for this change.** `search()` has no relevance threshold
today: every mode returns its top-`k` candidates by score regardless of
how weak that score is, so a `negative` query will still get 5 results
back, just (expectedly) low-scoring and uncorrelated with the query.
Because `recall_at_k`/`mrr` treat empty `expected` as trivially
satisfied, that's already consistent with the query set's intent
("nothing *relevant* is returned" — not "nothing is returned"). Whether
a minimum-score floor should suppress those weak results entirely is a
real product question, but it changes `search()`'s return contract
(stage 4's surface, frozen by this change's constraints) and belongs in
its own change if the sweep's negative-category rows ever show scores
close enough to real hits to be misleading — this stage only measures
and reports, it doesn't add the floor.

**Why the eval precedes the CLI and MCP stages.** Once a CLI command or
an MCP tool exists on top of `search()`, the temptation to compensate
for weak retrieval by tuning result limits, snippet length, or prompt
wording becomes available — and once that compensation happens, a
later retrieval measurement can no longer cleanly attribute good or bad
numbers to the retrieval design itself, because interface-layer choices
are now part of what's being measured. Doing the eval first means
`default_vector_weight` and `fusion_strategy` are chosen from retrieval
behavior alone, and every later stage inherits a configuration that was
never tuned against, or hidden by, a layer built on top of it.

## Risks / Trade-offs

**[Risk] The fixture corpus is synthetic — these numbers characterize
the retrieval design, not real vacancy data.** → Documented explicitly
in the README rather than implied away: the fixture vault's proper
nouns, phrasing patterns, and document lengths are generator artifacts
(`tests/fixtures/generate.py`), not a sample of real job-search
correspondence. A second eval run against a real vault after import
(stage 9) is named in the README as the number that will actually
generalize; this stage's numbers only justify a *default*, which
remains overridable per-deployment via `SearchConfig`'s existing
environment-variable seam if a real vault's numbers disagree.

**[Risk] `run_eval`'s full sweep issues ~360 `search()` calls (30
queries × 12 configs), and every semantic/hybrid call re-embeds the
query text from scratch — `search.py` has no query-embedding cache, and
this change isn't allowed to add one there.** → Accepted: `fastembed`
loads its model once per process and per-call inference on a single
short string is fast; the sweep is a developer-invoked or CI-time
operation, not a hot path. If sweep runtime ever threatens the CI job
time limit, the fix is a smaller `configs` sequence for CI (see
`run_eval`'s `configs` parameter) — the query set and metrics stay
exactly as tested either way.

**[Risk] Setting `SEARCH_FUSION_STRATEGY` via `os.environ` around each
hybrid call is process-global, not thread-local.** → Accepted:
`run_eval` runs its sweep sequentially in one process, and the context
manager restores the prior value immediately after each call, so no
call ever observes another call's in-flight override. This would need
revisiting only if the runner were ever parallelized, which it isn't
here.

**[Risk] Directly asserting the three "expected shape of findings"
scenarios means a future fixture-generator change could silently start
failing them.** → Intentional per the brief: these are the claims the
project makes about its own retrieval design, so a failure here is a
finding to report (in the README, per the brief), not a test to
loosen. If fixture content changes in a later stage in a way that flips
one of these directional results, that's exactly the kind of regression
this suite exists to catch.
