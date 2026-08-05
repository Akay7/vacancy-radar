## Context

Stage 3 (`index-build`) gives us a LanceDB table — one row per document
plus one per vacancy, denormalized vacancy fields on every row, a vector
column sized to the configured embedding model, and an FTS index on
`text` rebuilt on every `build_index` call. Nothing queries it yet. This
stage adds `search()`: three modes (keyword, semantic, hybrid), five
structured filters compiled to predicates, tunable fusion, and a snippet
extractor — all read-only, all reachable from a stable API stage 5 (the
eval harness) can measure against without also having to co-evolve it.

Two things this stage needs that stage 3 didn't provide:

1. **Embedding-model provenance.** Semantic search must embed the query
   with whatever model actually built the index's vectors — never a
   default that might have drifted since the last build. Nothing in
   stage 3's table records that fact anywhere queryable. This stage adds
   the minimum necessary: schema metadata stamped at table-creation time.
2. **A fusion architecture that exposes per-path ranks.** LanceDB's own
   `LanceHybridQueryBuilder` (`table.search(query, query_type="hybrid")`)
   runs both paths and reranks internally, but its result table doesn't
   surface each candidate's rank *within* each path — only the final
   fused order. `SearchHit.keyword_rank`/`semantic_rank` need that, so
   this stage runs both paths itself and reuses LanceDB's reranker
   classes (`RRFReranker`, `LinearCombinationReranker`) directly against
   the two raw per-path tables it already has in hand.

## Goals / Non-Goals

**Goals:**
- One `search()` entry point covering keyword, semantic, and hybrid
  retrieval, with structured filters compiled to predicates the LanceDB
  query engine pushes down — never post-filtered.
- Hybrid fusion that is swappable (RRF default, Linear Combination
  alternative) via config, without a `search.py` code change, so stage 5
  can sweep both from data.
- Deterministic ordering (including tie-breaks) and bounded, UTF-8-safe
  snippets that never influence ranking.
- Typed, actionable errors for every documented failure mode — no bare
  `RuntimeError` leaking a Rust panic message up through the API.
- Keyword mode that never pays the embedding model's load cost.

**Non-Goals:**
- Any measurement of retrieval quality, a query set, or recall metrics
  (stage 5).
- A reranker, cross-encoder, or query expansion.
- Boolean query-string parsing (`AND`/`OR`) — Lance FTS doesn't support
  it in the query string, and structured conditions already have a home:
  the filter parameters.
- A CLI or MCP surface (stages 8–9).
- Fully closing the pre-existing stage-3 gap where a same-dimension model
  swap without `force=True` under-re-embeds (see Risks).

## Decisions

**Filters compile to SQL predicates pushed into the query, never
post-filtered.** `search()`'s `.where(predicate, prefilter=True)` call
runs before LanceDB applies `.limit()`, so a `limit=10` filtered query
that has 10+ matching rows always returns 10. Post-filtering — running
the query unfiltered, then dropping non-matching rows from a fetched
top-`k` — has a silent failure mode: filtering *after* the top-k cut can
return fewer than `k` results even when more than `k` matching documents
exist, because rows that would have matched the filter never made it
into the fetched `k` in the first place. `company_slug`, `status`
(`IN (...)`), `kind` (`IN (...)`), `tags` (`array_has_any(tags, [...])`,
confirmed working against LanceDB 0.36's DataFusion-backed filter
engine), and `since` (`date >= '...'`) each compile independently and
`AND`-compose into one predicate string; an empty filter set means no
`.where()` call at all.

**RRF is the default fusion; Linear Combination is the selectable
alternative — both use LanceDB's own reranker classes.** `vector_weight`
is meaningful only under Linear Combination (`LinearCombinationReranker`
takes a `weight` in `[0, 1]`); RRF is rank-based and weight-agnostic by
construction (`RRFReranker`'s score is `Σ 1/(rank + K)` across whichever
paths a candidate appears in — no weight term). This is exactly the
brief's framing: "the LinearCombination alternative is selectable and
takes vector_weight." `SearchResults.effective_vector_weight` is `None`
under keyword, semantic, or hybrid-with-RRF, and the resolved float under
hybrid-with-LinearCombination. Stage 5's job is to measure which fusion
wins on this corpus; this stage's job is only to make the choice
reversible via `SearchConfig.fusion_strategy`, not to guess at it.
Alternative considered: a weighted-RRF variant (`vector_weight` scaling
each path's `1/(rank+K)` term) would let one `vector_weight` knob drive
both strategies uniformly — rejected as an unnecessary third fusion
formula stage 5 didn't ask to measure, when reusing LanceDB's two
existing, tested reranker classes verbatim is simpler and no less
capable of the required behavior (ordering changes with `vector_weight`,
extremes degenerate toward single-mode orderings — both properties hold
under Linear Combination as specified).

**Hybrid mode runs both paths itself, not `table.search(..., query_type="hybrid")`.**
`LanceHybridQueryBuilder.to_arrow()` internally fetches an FTS table and a
vector table, normalizes their scores, and calls a reranker's
`rerank_hybrid(query, vector_results, fts_results)` — but never exposes
the two raw per-path tables it built along the way, only the final fused
one. Since `SearchHit` needs each candidate's 1-based position in *each*
path independently (`keyword_rank`, `semantic_rank`, `None` when absent),
`search()`'s hybrid branch fetches the FTS table
(`table.search(text, query_type="fts").where(pred, prefilter=True).with_row_id(True).limit(pool_size)`)
and the vector table
(`table.search(vector, query_type="vector").where(pred, prefilter=True).with_row_id(True).limit(pool_size)`)
itself, derives `keyword_rank`/`semantic_rank` from each table's row
order (both already come back sorted by their own score), and *then*
calls `RRFReranker().rerank_hybrid(...)` or
`LinearCombinationReranker(weight=...).rerank_hybrid(...)` — LanceDB's
own tested fusion math, not reimplemented, just fed by queries we already
had to run to get per-path ranks. `pool_size` is
`min(max(limit * CANDIDATE_POOL_MULTIPLIER, MIN_CANDIDATE_POOL), CANDIDATE_POOL_CAP)`,
implemented with `CANDIDATE_POOL_MULTIPLIER = 5`, `MIN_CANDIDATE_POOL =
50`, `CANDIDATE_POOL_CAP = 200` — a fixed overfetch per path so fusion
has enough overlap to work with before the final slice to `limit`;
`SearchResults.total_candidates` is
the size of the union of both pools before that slice, giving a real
(not `== len(hits)`) diagnostic number specifically for hybrid. Keyword
and semantic (single-path) modes need no overfetch — predicate pushdown
plus `.limit(limit)` already returns up to exactly `limit` rows in one
call, so `total_candidates == len(hits)` there.

**Scores are always "higher is better," normalized per mode.** Keyword
mode returns BM25's native `_score` untouched (already higher-is-better,
satisfying "Scores are BM25-derived and ordered descending" directly).
Semantic mode's vector query explicitly sets `distance_type="cosine"`
(LanceDB's default is L2) and reports `1 - _distance` as `score`, so
"ordered descending" holds the same way across all three modes without a
mode-specific comparator in any caller. Hybrid reports the reranker's
`_relevance_score`, which both `RRFReranker` and `LinearCombinationReranker`
already produce as higher-is-better and sorted descending.

**The embedding model is recorded once, at table-creation time, in Arrow
schema metadata — not a new column, not a sidecar file.**
`_open_or_create_table` (stage 3, `build.py`) builds its schema as
`build_schema(dim).to_arrow_schema().with_metadata({b"embedding_model": model_name.encode()})`
whenever it actually creates a table (fresh build, or the existing
dimension-mismatch recreate path) — confirmed empirically that LanceDB
persists and returns Arrow schema metadata across `connect()`/
`open_table()` round-trips. `search.py` reads it back via
`table.schema.metadata.get(b"embedding_model")`. Why schema metadata over
alternatives: a new `embedding_model` *column* would mean per-row
duplication of a table-level fact and would need backfilling on every
existing row on every build; a separate one-row "meta" table would be a
second table to keep in sync with the first and to remember to delete
alongside `.index/` for disposability. Schema metadata travels with the
table by construction — delete `.index/` and rebuild, and the new
table's metadata is correct by the same code path that already handles
dimension changes, with zero extra bookkeeping.

**A mismatch is caught by comparing the recorded model against the
codebase's current default, before ever embedding the query.**
`search()`'s semantic/hybrid branches read `index_model` from schema
metadata and compare it to `vacancy_radar.index.embed.DEFAULT_EMBEDDING_MODEL_NAME`
— the single source of truth for "what this codebase would otherwise
embed with." If they differ (or `index_model` is absent — an index built
before this stage shipped), `EmbeddingModelMismatchError(index_model,
expected_model)` is raised *before* any embedding call, naming both
models. The query is then always embedded with `index_model` (never a
default) precisely because that comparison already guaranteed they agree
by the time embedding happens — the two clauses in the requirement
("embedded with the recorded model, not a default" and "a mismatch
raises") aren't in tension: the second is what guarantees the first is
also always correct, rather than the two being independent behaviors.
Silently embedding queries with whatever the *current* default happens to
be — without checking what the index was actually built with — is
exactly the "quietly wrong results" failure mode: two embedding models
can and do share an output dimension (e.g. many 384-dim sentence
encoders), so a mismatched model wouldn't raise a dimension error from
LanceDB; it would return plausible-looking, meaningless nearest
neighbors, indistinguishable from a real result set without this check.

**Phrase-query positions (`FTS(with_position=True)`) are left disabled in
this stage.** No requirement in this stage's scenarios needs phrase
matching, and stage 3's `build_index` already creates its FTS index with
LanceDB's default (`with_position=False`). Enabling it would mean
modifying `build.py`'s `create_index` call — a real behavior change to
stage 3 beyond the minimal, necessary provenance amendment above — for a
capability nothing here tests. At this corpus's scale the storage cost of
enabling it would be negligible if a future stage's requirements need
phrase queries; that's the point at which to make this change, informed
by an actual phrase-query requirement rather than speculatively now.

**`search()`'s `mode`, `limit`, and `vector_weight` default to `None` at
the Python level, resolving against `SearchConfig` inside the function
body — not baked in as literal Python parameter defaults.** A literal
default (`limit: int = 10`) is fixed at function-definition time; nothing
stage 5 does to `SearchConfig` after that point would change it, which
directly contradicts "Stage 5 will change these from data ... without
touching search.py." `None` is an unambiguous sentinel here (a caller who
wants literally `mode=None` isn't a real case — `SearchMode` has no such
value), so `search(index, query, mode=None, ...)` and `search(index,
query)` behave identically: both resolve `mode` from
`resolve_search_config()` at call time. Passing an explicit value (e.g.
`mode=SearchMode.KEYWORD`) always overrides config for that one call,
same as before. `resolve_search_config()` mirrors `resolve_vault_path`'s
existing env-var-precedence pattern: `SEARCH_DEFAULT_MODE`,
`SEARCH_DEFAULT_VECTOR_WEIGHT`, `SEARCH_DEFAULT_LIMIT`,
`SEARCH_FUSION_STRATEGY`, each falling back to `SearchConfig`'s field
default when unset — so stage 5 can retune defaults either by setting
env vars per run or by constructing and passing a `SearchConfig`
directly to a caller that isn't `search()` itself (the eval harness),
without editing `search.py` either way.

**Snippet extraction is a pure, presentation-only function over already-
ranked hits — it never reads from or writes back into the ranking path.**
`extract_snippet(text, query, *, has_keyword_match)` finds the first
case-insensitive literal occurrence of a query term in `text` and returns
a fixed-size window (`SNIPPET_MAX_CHARS = 200`) of `str` (Unicode
codepoints, not bytes) centered on it; a semantic-only hit
(`has_keyword_match=False`, `search()` passes this whenever a hit's
`keyword_rank is None`) or a keyword hit whose match came from FTS
stemming rather than a literal substring (no query term appears
verbatim) falls back to the document's opening
`text[:SNIPPET_MAX_CHARS]`. Slicing a Python `str` by codepoint index can
never split a multi-byte UTF-8 character, because a `str` index always
addresses a whole codepoint — the "never split a UTF-8 character"
requirement is a property of operating on `str` throughout, not something
`extract_snippet` has to additionally guard against. `search()` calls it
once per hit, strictly after fusion and ordering are finalized, so no
snippet-extraction outcome can ever change which hit ranks where.

## Risks / Trade-offs

- [A same-dimension model swap (`model_name` changes, `vector_dim`
  doesn't) without `force=True` leaves existing unchanged-hash rows
  un-re-embedded, while `_open_or_create_table` reuses the existing table
  and its now-stale recorded metadata] → Pre-existing stage-3 diffing
  behavior, not introduced by this change; this stage's mismatch check
  still protects the common case (build fresh, or always pair a model
  change with `force=True`) and is strictly better than recording
  nothing. Fully closing it (detecting "model_name changed, dimension
  didn't" and forcing a full re-embed) belongs to a stage-3-scoped fix
  informed by whether that scenario actually recurs in practice.
- [Hybrid mode's overfetch (`pool_size` per path) adds two LanceDB round
  trips instead of one, and a `CANDIDATE_POOL_CAP` bounds worst-case
  latency at the cost of a hard ceiling on fusion visibility for very
  large `limit` values] → Acceptable at this corpus's scale (a few
  hundred milliseconds target over ~700 vacancies); revisit the constants
  if stage 5's measurement runs need a larger `limit` than the cap
  comfortably supports.
- [`vector_weight` is silently inert when `fusion_strategy` is RRF —
  a caller who passes it expecting an effect under the default fusion
  gets no error, just no visible change] → `effective_vector_weight` is
  `None` in `SearchResults` whenever it wasn't actually applied, so the
  return value is honest even though the call itself doesn't raise;
  documented directly in `search()`'s docstring and this design.
- [The query-length truncation warning uses a whitespace-token count
  heuristic against a fixed constant, not each model's actual tokenizer
  limit] → `fastembed`'s `TextEmbedding` doesn't expose a stable, public
  max-sequence-length field per model (only free-text model descriptions
  mention it), and adding a tokenizer dependency to compute exact subword
  counts is out of scope (no new runtime dependencies). The ONNX model
  itself truncates over-length input at its own tokenizer layer
  regardless, so the heuristic's only job is surfacing a warning, not
  preventing a crash — a conservative word-count threshold
  (`QUERY_LENGTH_WARNING_THRESHOLD_WORDS = 400`, comfortably under
  `bge-small-en-v1.5`'s 512-subword-token limit even accounting for
  words that split into multiple subword tokens) under-warns rather
  than over-warns, which is the safer failure direction for a
  non-fatal advisory.

## Migration Plan

Additive within an already-disposable index: the schema-metadata amendment
only takes effect on a table's next *creation* (fresh build, or a
dimension-driven recreate) — an index already built under the pre-this-
stage schema has no `embedding_model` metadata until it's rebuilt, at
which point `search()`'s semantic/hybrid modes raise
`EmbeddingModelMismatchError` with `index_model=None`, naming the fix
(rebuild the index) rather than guessing. No committed index artifact
exists to migrate (`.index/` is gitignored and disposable by design); the
committed `tests/fixtures/vault/` tree gains new fixture content (rare
term, distinctive noun, paraphrase pair) but no structural change to
existing fixtures, so no existing test's fixed expectations should need
updating beyond what the new content itself requires.

## Open Questions

None outstanding. The two points that could have blocked this
(embedding-model provenance having nowhere to live, and per-path ranks
being unavailable from LanceDB's built-in hybrid query) are resolved
above rather than left for implementation time to improvise.
