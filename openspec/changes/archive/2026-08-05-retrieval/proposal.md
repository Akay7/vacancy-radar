## Why

Stage 3 gives us a LanceDB table with BM25 and vector search available on
it, but nothing yet turns that into a callable query. Nothing in the vault
or the index is discoverable until a function exists that runs a query
against the table and returns ranked, filterable results. Stage 5's eval
harness needs a finished retrieval API to measure — not a moving target —
so this stage builds `search()` on its own, deliberately ahead of and
separate from any measurement of how good it is.

## What Changes

- Add `src/vacancy_radar/index/search.py`: `SearchMode` (`keyword`,
  `semantic`, `hybrid`), `search()`, `SearchResults`, `SearchHit`, and a
  small family of typed errors (`EmptyQueryError`, `InvalidLimitError`,
  `MissingFTSIndexError`, `EmbeddingModelMismatchError`).
  - `keyword` runs LanceDB FTS (BM25) only; never loads the embedding
    model.
  - `semantic` embeds the query with the model recorded in the index (not
    a default) and runs vector similarity only.
  - `hybrid` runs both paths independently, keeping each path's own rank
    per candidate, then fuses with a swappable strategy — Reciprocal Rank
    Fusion (RRF) by default, Linear Combination (`vector_weight`-driven)
    as the selectable alternative. Stage 5 decides which wins from
    measurement; this stage only makes both reachable and the choice
    reversible via config.
  - `company_slug`, `status`, `kind`, `tags`, `since` compile to SQL
    predicates pushed into the LanceDB query (`prefilter=True`) against
    the schema's denormalized columns — never applied by post-filtering a
    fetched result set, which would silently return fewer than `limit`.
  - Every `SearchHit` reports `keyword_rank`/`semantic_rank` (its 1-based
    position in that path's own ranked candidates, `None` when the hit
    didn't appear in that path), independent of which fusion strategy
    combined them.
- Add `src/vacancy_radar/index/snippet.py`: `extract_snippet` — a
  deterministic, presentation-only window around the best literal query
  match, falling back to the document's opening text for semantic-only
  hits. Bounded length; operates on `str` (Unicode codepoints), so a
  window boundary never lands inside a multi-byte UTF-8 character.
- Amend `src/vacancy_radar/config.py`: `SearchConfig` (`default_mode`,
  `default_vector_weight`, `default_limit`, `fusion_strategy`) and
  `resolve_search_config()`, following the existing
  explicit-then-env-var-then-default precedence
  (`resolve_vault_path`'s pattern) so stage 5 can retune defaults from
  measurement data without editing `search.py`.
- **Index-schema amendment (MODIFIED delta on `index-schema`)**: the table
  created by `build_index` now records the embedding model that built it
  in its Arrow schema metadata. Nothing before this stage persisted that
  fact anywhere queryable, and semantic/hybrid search cannot embed a query
  compatibly without reading it back.
- **Index-build amendment (MODIFIED delta on `index-build`)**:
  `_open_or_create_table` stamps the current `model_name` into the new
  table's schema metadata whenever it creates one (fresh build, or a
  dimension-driven recreate). An existing, reused table's metadata is left
  untouched — the same trust boundary the dimension-recreate logic already
  relies on (see design.md's Risks for the pre-existing gap this doesn't
  close: a same-dimension model swap without `force=True` still under-
  re-embeds, independent of this change).
- Extend `tests/fixtures/generate.py` with fixed (non-random), deterministic
  additions the fixture vault didn't previously need: a distinctive proper
  noun appearing in exactly one document, a rare technology term alongside
  a topically-adjacent-but-distinct one (to prove specificity, not just
  presence), and a paraphrase pair — one document phrased in
  domain-specific language, one query string sharing no content words with
  it — so the semantic-mode test has a case keyword mode structurally
  cannot serve. These are appended unconditionally (like the healthy tree,
  not opt-in like `--broken`), so `tests/fixtures/vault/` is regenerated
  and recommitted as part of this change.

## Capabilities

### New Capabilities
- `search`: `SearchMode`, `search()`, `SearchResults`/`SearchHit`,
  predicate-pushdown filtering, per-path rank tracking, RRF/Linear
  Combination fusion, and the typed error family for empty queries,
  invalid limits, a missing FTS index, and an embedding-model mismatch.
- `snippet-extraction`: `extract_snippet` — deterministic keyword-window
  extraction with a document-opening fallback, bounded and UTF-8-safe,
  with no influence on ranking.
- `search-config`: `SearchConfig` and `resolve_search_config()` —
  environment-overridable defaults for mode, vector weight, limit, and
  fusion strategy, settable without touching `search.py`.

### Modified Capabilities
- `index-schema`: the table's schema metadata now records the embedding
  model that built it, so a reader can recover that fact without
  out-of-band bookkeeping.
- `index-build`: table creation (fresh build or dimension-driven
  recreate) stamps the active `model_name` into that new metadata.

## Impact

- New files: `src/vacancy_radar/index/search.py`,
  `src/vacancy_radar/index/snippet.py`, plus `tests/index/test_search.py`
  and `tests/index/test_snippet.py`.
- Modified: `src/vacancy_radar/config.py` (new `SearchConfig`/
  `resolve_search_config`, additive — `resolve_vault_path` and its errors
  are untouched), `src/vacancy_radar/index/schema.py` and
  `src/vacancy_radar/index/build.py` (embedding-model provenance in
  schema metadata, additive to the existing table-creation path),
  `tests/fixtures/generate.py` and the committed `tests/fixtures/vault/`
  tree (new deterministic fixtures for keyword specificity and semantic
  paraphrase scenarios), `tests/config/test_config.py` (or equivalent) for
  the config amendment.
- No new runtime dependencies — `search.py` and `snippet.py` are built
  entirely on `lancedb` and `fastembed`, already present since stage 3.
- No CLI or MCP surface (stages 8–9). No reranker, cross-encoder, or query
  expansion. No eval harness, recall metric, or query set (stage 5).
- Read-only with respect to the vault and to existing index data: nothing
  in `search.py`/`snippet.py` writes anything. The one write path touched
  is `build_index`'s table-*creation* moment (not a per-search write),
  which already existed in stage 3 and is unrelated to running a query.
