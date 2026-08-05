## 1. Fixture vault: distinctive-noun and rare-term content — tests, then implementation

- [x] 1.1 Write `tests/fixtures/test_generate.py` (extend if it exists,
      else create): the generated vault contains exactly one document
      whose text includes a fixed, distinctive proper noun (not drawn
      from any existing name pool)
- [x] 1.2 Write `tests/fixtures/test_generate.py`: the generated vault
      contains at least one document containing a fixed rare technology
      term, and at least one other document containing a different,
      topically adjacent term but not the rare term itself
- [x] 1.3 Run tests, confirm they fail (fixture content doesn't exist yet)
- [x] 1.4 Implement in `tests/fixtures/generate.py`: a
      `write_search_fixtures(vault_dir: Path) -> None` function adding a
      fixed (non-random) company/vacancy/document tree carrying the
      distinctive proper noun and the rare-term/adjacent-term pair,
      following `write_broken_fixtures`'s pattern of a distinct,
      non-colliding company slug; call it unconditionally from `main()`
      (not gated behind `--broken` — this content is required baseline
      fixture, not a resilience fixture)
- [x] 1.5 Re-run 1.1–1.2 and confirm they pass

## 2. Fixture vault: semantic paraphrase pair — tests, then implementation

- [x] 2.1 Write `tests/fixtures/test_generate.py`: the generated vault
      contains a target document phrased in domain-specific language, and
      a module-level exported paraphrase query constant sharing no
      content words with that document's text
- [x] 2.2 Run the test, confirm it fails
- [x] 2.3 Extend `write_search_fixtures` (or a sibling function) to add
      the paraphrase-target document and export
      `SEMANTIC_PARAPHRASE_QUERY` (and the target's fixed `doc_id`) as
      module-level constants tests can import
- [x] 2.4 Re-run 2.1 and confirm it passes

## 3. Regenerate and commit the fixture vault

- [x] 3.1 Run `python tests/fixtures/generate.py` to regenerate
      `tests/fixtures/vault/` with the new content from sections 1–2.
      Correction from the plan: `--broken` fixtures were never part of
      the committed tree (confirmed via `git ls-files` and
      `fixture-generation`'s spec — `--broken` is generate-on-the-fly
      only, used transiently by vault-reader/build's own tmp-path
      tests), so the committed tree gets only the healthy tree plus
      `write_search_fixtures`'s unconditional addition
- [x] 3.2 Run the full existing test suite (`uv run pytest -m "not
      embedding"`) to confirm no prior stage's tests broke from the
      fixture tree changing shape — 145 passed, 22 deselected
- [x] 3.3 Review the fixture diff; commit only the intended new files/
      content, no incidental regeneration drift — confirmed via `git
      status`/`git diff`: only `tests/fixtures/vault/search-fixtures-corp/`
      is new, every pre-existing file byte-identical (after running
      `pre-commit run end-of-file-fixer` to restore the trailing
      newline convention the raw generator run doesn't apply)

## 4. index-schema / index-build: embedding-model provenance — tests, then implementation

- [x] 4.1 Write `tests/index/test_schema.py`: a table created with a
      given `model_name`'s schema metadata (`to_arrow_schema().with_metadata(...)`)
      carries that model name under a fixed key, readable after a fresh
      `connect()`/`open_table()`
- [x] 4.2 Write `tests/index/test_build.py`: a fresh `build_index` call
      records the `model_name` it was called with in the resulting
      table's schema metadata
- [x] 4.3 Write `tests/index/test_build.py`: a `build_index` call that
      triggers the existing dimension-mismatch recreate path (different
      `model_name`, different `vector_dim`) records the *new*
      `model_name`, not the old one
- [x] 4.4 Write `tests/index/test_build.py`: an incremental `build_index`
      call with an unchanged `model_name` (no table recreation) leaves
      the table's recorded metadata unchanged
- [x] 4.5 Run tests, confirm they fail
- [x] 4.6 Implement in `src/vacancy_radar/index/schema.py`: a small
      helper to attach `{b"embedding_model": model_name.encode()}` to a
      schema's Arrow form, and a `read_embedding_model(table) -> str |
      None` reader
- [x] 4.7 Implement in `src/vacancy_radar/index/build.py`:
      `_open_or_create_table` passes the metadata-carrying Arrow schema
      to `connection.create_table(...)` on both create branches (fresh,
      and dimension-mismatch recreate); the reused-table branch is
      untouched
- [x] 4.8 Re-run 4.1–4.4 and confirm they pass; re-run stage 3's full
      `test_build.py`/`test_schema.py` suite to confirm no regression

## 5. config.py: SearchConfig and resolve_search_config — tests, then implementation

- [x] 5.1 Write `tests/test_config.py` (extend if it exists, else
      create): `SearchConfig()` constructs with its documented defaults
      (`default_mode=HYBRID`, a documented `default_vector_weight`,
      `default_limit=10`, `fusion_strategy=RRF`)
- [x] 5.2 Write `tests/test_config.py`: with none of
      `SEARCH_DEFAULT_MODE`/`SEARCH_DEFAULT_VECTOR_WEIGHT`/
      `SEARCH_DEFAULT_LIMIT`/`SEARCH_FUSION_STRATEGY` set,
      `resolve_search_config()` returns a `SearchConfig` equal to
      `SearchConfig()`
- [x] 5.3 Write `tests/test_config.py`: setting each of the four
      environment variables individually overrides only that field in
      the resolved `SearchConfig`, leaving the other three at their
      field defaults
- [x] 5.4 Write `tests/test_config.py`: an invalid value for
      `SEARCH_DEFAULT_MODE` or `SEARCH_FUSION_STRATEGY` (not a valid
      enum member) raises a clear, typed error rather than silently
      falling back
- [x] 5.5 Run tests, confirm they fail (module doesn't exist yet)
- [x] 5.6 Implement in `src/vacancy_radar/config.py`: `SearchMode`-
      independent `FusionStrategy` `StrEnum` (`RRF`, `LINEAR_COMBINATION`),
      `SearchConfig` frozen dataclass, `resolve_search_config()` following
      `resolve_vault_path`'s environment-then-field-default precedence
      (note: `SearchMode` itself is defined in `search.py`, per the
      deliverable; `config.py` imports it for `SearchConfig.default_mode`'s
      type, no circular import since `search.py` does not import
      `config.py` at module scope for this — see 6.1's ordering note)
- [x] 5.7 Re-run 5.1–5.4 and confirm they pass

## 6. search.py: module skeleton — SearchMode, exceptions, SearchHit, SearchResults

- [x] 6.1 Write `tests/index/test_search.py`: `SearchMode` has exactly
      `KEYWORD`, `SEMANTIC`, `HYBRID` members; importing
      `vacancy_radar.index.search` and `vacancy_radar.config` together
      does not raise `ImportError` (confirms no circular import between
      `SearchMode`'s definition and `config.py`'s reference to it)
- [x] 6.2 Write `tests/index/test_search.py`: `SearchResults` and
      `SearchHit` construct with the fields specified in proposal.md
      (`hits`, `mode`, `effective_vector_weight`, `elapsed_ms`,
      `total_candidates` on `SearchResults`; `doc_id`, `vacancy_id`,
      `company`, `company_slug`, `role`, `status`, `kind`, `path`, `date`,
      `score`, `snippet`, `keyword_rank`, `semantic_rank` on `SearchHit`)
- [x] 6.3 Run tests, confirm they fail (module doesn't exist yet)
- [x] 6.4 Implement `src/vacancy_radar/index/search.py`: `SearchMode`
      (`StrEnum`), `SearchError` base exception and
      `EmptyQueryError`/`InvalidLimitError`/`MissingFTSIndexError`/
      `EmbeddingModelMismatchError` subclasses (each composing a message
      naming the fix, following `VaultNotFoundError`'s `reason` pattern),
      `SearchHit`/`SearchResults` frozen dataclasses
- [x] 6.5 Re-run 6.1–6.2 and confirm they pass

## 7. search.py: query and limit validation — tests, then implementation

- [x] 7.1 Write `tests/index/test_search.py`: an empty or whitespace-only
      query raises `EmptyQueryError` for every mode, before any index
      access
- [x] 7.2 Write `tests/index/test_search.py`: `limit=0` returns
      `SearchResults` with an empty `hits` list, no exception
- [x] 7.3 Write `tests/index/test_search.py`: a negative `limit` raises
      `InvalidLimitError`
- [x] 7.4 Run tests, confirm they fail
- [x] 7.5 Implement validation at the top of `search()`: query
      strip-and-check, limit sign check, `limit == 0` short-circuit
      returning an empty `SearchResults` without touching the table
- [x] 7.6 Re-run 7.1–7.3 and confirm they pass

## 8. search.py: predicate builder and filter pushdown — tests, then implementation

- [x] 8.1 Write `tests/index/test_search.py`: the internal predicate
      builder produces the expected SQL fragment for each filter kind in
      isolation (`company_slug` equality, `status` `IN (...)`, `kind`
      `IN (...)`, `tags` `array_has_any(...)`, `since` as `date >=
      '...'`) and `AND`-joins them when more than one is given; no
      filters given produces no `.where()` call at all
- [x] 8.2 Write `tests/index/test_search.py`: `company_slug` excludes
      other companies' documents (against the fixture vault, `mode=KEYWORD`
      for speed)
- [x] 8.3 Write `tests/index/test_search.py`: `status` given a list
      returns the union of matching statuses
- [x] 8.4 Write `tests/index/test_search.py`: `kind` restricts to the
      given kinds
- [x] 8.5 Write `tests/index/test_search.py`: `tags` restricts to
      documents carrying at least one given tag
- [x] 8.6 Write `tests/index/test_search.py`: `since` excludes documents
      dated earlier
- [x] 8.7 Write `tests/index/test_search.py`: combining `company_slug`
      and `status` together returns only documents satisfying both, not
      the union of either alone
- [x] 8.8 Write `tests/index/test_search.py`: a filter combination
      matching no document returns an empty `hits` list, no exception
- [x] 8.9 Write `tests/index/test_search.py`: a filter matched by more
      documents than `limit` still returns exactly `limit` hits
      (predicate-pushdown proof)
- [x] 8.10 Run tests, confirm they fail
- [x] 8.11 Implement an internal `_build_predicate(...) -> str | None` in
      `search.py`, and thread it through as `.where(predicate,
      prefilter=True)` wherever a query is issued
- [x] 8.12 Re-run 8.1–8.9 and confirm they pass

## 9. search.py: FTS-index-presence guard — tests, then implementation

- [x] 9.1 Write `tests/index/test_search.py`: a table with no full-text
      index created on `text` raises `MissingFTSIndexError` (message
      naming `build_index` as the fix) under `mode=KEYWORD` or
      `mode=HYBRID`, before issuing the FTS query
- [x] 9.2 Run the test, confirm it fails
- [x] 9.3 Implement a proactive check (`table.list_indices()`, looking
      for an `FTS`-typed index on `text`) before any FTS query, raising
      `MissingFTSIndexError` instead of letting LanceDB's raw error
      propagate
- [x] 9.4 Re-run 9.1 and confirm it passes

## 10. search.py: keyword mode — tests, then implementation

- [x] 10.1 Write `tests/index/test_search.py`: an exact company name
      query under `mode=KEYWORD` returns that company's documents
- [x] 10.2 Write `tests/index/test_search.py`: the fixture's distinctive
      proper noun (section 1) ranks its sole document first
- [x] 10.3 Write `tests/index/test_search.py`: the fixture's rare
      technology term (section 1) returns the document containing it and
      excludes the document containing only the adjacent term
- [x] 10.4 Write `tests/index/test_search.py`: a query matching nothing
      returns an empty `hits` list, no exception
- [x] 10.5 Write `tests/index/test_search.py`: keyword scores are
      non-increasing across the returned hit list
- [x] 10.6 Write `tests/index/test_search.py` (instrumented, per design):
      a `mode=KEYWORD` call never triggers an embedding-model load
- [x] 10.7 Run tests, confirm they fail
- [x] 10.8 Implement the keyword branch: `table.search(query,
      query_type="fts").where(predicate, prefilter=True).limit(limit)`,
      mapping rows to `SearchHit` with `keyword_rank` set from result
      order and `semantic_rank=None`, `score` from `_score` directly
- [x] 10.9 Re-run 10.1–10.6 and confirm they pass

## 11. search.py: embedding-model resolution and mismatch guard — tests, then implementation

- [x] 11.1 Write `tests/index/test_search.py` (marked `embedding`): an
      index whose recorded model matches
      `vacancy_radar.index.embed.DEFAULT_EMBEDDING_MODEL_NAME` embeds the
      query with that recorded model under `mode=SEMANTIC`
- [x] 11.2 Write `tests/index/test_search.py`: an index whose recorded
      model differs from the current default raises
      `EmbeddingModelMismatchError` naming both models, before any
      embedding call, under `mode=SEMANTIC` and `mode=HYBRID`
- [x] 11.3 Write `tests/index/test_search.py`: a table with no recorded
      `embedding_model` in schema metadata raises the same typed error
      under `mode=SEMANTIC` and `mode=HYBRID`
- [x] 11.4 Run tests, confirm they fail
- [x] 11.5 Implement `_resolve_query_embedding_model(table) -> str`:
      reads `schema.read_embedding_model(table)`, compares against
      `embed.DEFAULT_EMBEDDING_MODEL_NAME`, raises
      `EmbeddingModelMismatchError` on disagreement (including `None`),
      otherwise returns the (now-confirmed-matching) recorded model name
- [x] 11.6 Re-run 11.1–11.3 and confirm they pass

## 12. search.py: semantic mode — tests, then implementation

- [x] 12.1 Write `tests/index/test_search.py` (marked `embedding`): the
      paraphrase query from section 2 returns its target document under
      `mode=SEMANTIC`
- [x] 12.2 Write `tests/index/test_search.py` (marked `embedding`): the
      same paraphrase query under `mode=KEYWORD` does not return the
      target document (proves the semantic case is real, not incidental
      lexical overlap)
- [x] 12.3 Write `tests/index/test_search.py` (marked `embedding`):
      semantic hits are ordered by `score` descending, `score` computed
      as `1 - cosine distance`
- [x] 12.4 Run tests, confirm they fail
- [x] 12.5 Implement the semantic branch: embed the query via
      `embed_texts([query], model_name=resolved_model)`,
      `table.search(vector, query_type="vector",
      distance_type="cosine").where(predicate,
      prefilter=True).limit(limit)`, mapping rows to `SearchHit` with
      `semantic_rank` from result order, `keyword_rank=None`, `score =
      1 - _distance`
- [x] 12.6 Re-run 12.1–12.3 and confirm they pass

## 13. search.py: hybrid mode — per-path ranks and fusion — tests, then implementation

- [x] 13.1 Write `tests/index/test_search.py` (marked `embedding`): every
      hybrid hit's `doc_id` appears in the keyword results, the semantic
      results, or both, for the same query
- [x] 13.2 Write `tests/index/test_search.py` (marked `embedding`): a
      query with one document strong under both keyword and semantic
      search ranks that document above one strong under only one
- [x] 13.3 Write `tests/index/test_search.py` (marked `embedding`): a
      hit present in both per-path candidate sets reports non-null
      `keyword_rank` and `semantic_rank`; a hit present in only one
      reports `None` for the other
- [x] 13.4 Write `tests/index/test_search.py` (marked `embedding`): under
      `fusion_strategy=LINEAR_COMBINATION`, two different `vector_weight`
      values produce two different hit orderings for the same query
- [x] 13.5 Write `tests/index/test_search.py` (marked `embedding`): under
      `fusion_strategy=LINEAR_COMBINATION`, `vector_weight` near 0
      approximates `mode=KEYWORD`'s ordering and near 1 approximates
      `mode=SEMANTIC`'s ordering (compare via rank-correlation or
      top-N-overlap, not exact equality)
- [x] 13.6 Write `tests/index/test_search.py` (marked `embedding`): under
      the default `fusion_strategy=RRF`, `SearchResults.effective_vector_weight`
      is `None` regardless of a passed `vector_weight`; under
      `LINEAR_COMBINATION` it equals the resolved weight
- [x] 13.7 Run tests, confirm they fail
- [x] 13.8 Implement the hybrid branch: compute `pool_size` from `limit`
      via the constants in design.md, run the FTS query and the vector
      query independently (each `with_row_id(True)`, same predicate,
      `.limit(pool_size)`), build `keyword_rank`/`semantic_rank` maps
      from each result's row order, call `RRFReranker().rerank_hybrid(...)`
      or `LinearCombinationReranker(weight=...).rerank_hybrid(...)`
      per `SearchConfig.fusion_strategy`, slice the fused table to
      `limit`, map to `SearchHit` joining in the rank maps and `score`
      from `_relevance_score`; set `total_candidates` to the size of the
      union of both pools
- [x] 13.9 Re-run 13.1–13.6 and confirm they pass

## 14. search.py: determinism and tie-breaking — tests, then implementation

- [x] 14.1 Write `tests/index/test_search.py`: calling `search` twice
      with identical arguments against an unmodified index returns hits
      with the same `doc_id`s in the same order both times, for each mode
- [x] 14.2 Write `tests/index/test_search.py`: a query engineered to
      produce two equal-`score` hits (e.g. two fixture documents with
      identical `text`) orders them by `doc_id` ascending, consistently
      across repeated calls
- [x] 14.3 Run tests, confirm they fail if tie-breaking isn't already
      stable (LanceDB's own ordering may already be stable for a fixed
      table state — treat a failure here as a real gap, not a missing-
      feature gap)
- [x] 14.4 Implement an explicit secondary sort key (`doc_id` ascending)
      applied after each mode's primary ordering, before slicing to
      `limit`
- [x] 14.5 Re-run 14.1–14.2 and confirm they pass

## 15. search.py: query-length truncation warning — tests, then implementation

- [x] 15.1 Write `tests/index/test_search.py` (marked `embedding`): a
      query far exceeding the configured word-count threshold emits a
      warning (`pytest.warns`) and `search` still completes and returns
      results under `mode=SEMANTIC`
- [x] 15.2 Write `tests/index/test_search.py`: a query under the
      threshold emits no such warning
- [x] 15.3 Run tests, confirm they fail
- [x] 15.4 Implement a whitespace-token count check against a module
      constant (documented in design.md as a conservative heuristic, not
      exact subword tokenization) before embedding, `warnings.warn(...)`
      when exceeded, no behavior change otherwise
- [x] 15.5 Re-run 15.1–15.2 and confirm they pass

## 16. snippet.py — tests, then implementation

- [x] 16.1 Write `tests/index/test_snippet.py`: a literal
      (case-insensitive) query-term match in the text produces a snippet
      containing that term
- [x] 16.2 Write `tests/index/test_snippet.py`: no literal match (or
      `has_keyword_match=False`) falls back to the text's opening,
      bounded to the configured maximum length
- [x] 16.3 Write `tests/index/test_snippet.py`: text containing
      multi-byte UTF-8 characters (Cyrillic, emoji) near a window
      boundary produces a snippet within the length bound that encodes to
      UTF-8 without error
- [x] 16.4 Write `tests/index/test_snippet.py`: calling `extract_snippet`
      twice with identical arguments returns an identical result
- [x] 16.5 Run tests, confirm they fail (module doesn't exist yet)
- [x] 16.6 Implement `src/vacancy_radar/index/snippet.py`:
      `SNIPPET_MAX_CHARS` constant, `extract_snippet(text, query, *,
      has_keyword_match) -> str` — locate the first case-insensitive
      literal occurrence of any whitespace-split query term, return a
      centered window (`str` slicing only, never encoding to bytes
      before slicing); fall back to `text[:SNIPPET_MAX_CHARS]`
- [x] 16.7 Re-run 16.1–16.4 and confirm they pass

## 17. search.py: snippet integration — tests, then implementation

- [x] 17.1 Write `tests/index/test_search.py`: a keyword hit's `snippet`
      contains the matched query term
- [x] 17.2 Write `tests/index/test_search.py` (marked `embedding`): a
      semantic-only hit's `snippet` equals its document's opening text
- [x] 17.3 Write `tests/index/test_search.py`: hit ordering is identical
      whether or not `snippet` values are inspected (snippet extraction
      has no effect on ranking — call `search` once, verify the `doc_id`
      order matches a `doc_id`-only projection of the same call)
- [x] 17.4 Run tests, confirm they fail
- [x] 17.5 Implement: call `extract_snippet` once per hit, strictly after
      each mode's ordering (and, for hybrid, after fusion) is finalized
- [x] 17.6 Re-run 17.1–17.3 and confirm they pass

## 18. Performance

- [x] 18.1 Write `tests/index/test_search.py` (marked `embedding`, since
      it needs a built large index): building an index from a generated
      ~700-vacancy vault (stage 2's scale override, stage 3's build
      path), then timing one `search` call per mode — each completes
      within a few hundred milliseconds
- [x] 18.2 Run the test, confirm it passes against the implementation
      from sections 7–17 (no separate implementation expected here); if
      it fails, treat as a real performance defect (e.g. an
      under-tuned `CANDIDATE_POOL_CAP`) rather than lowering the bar

## 19. Verification

- [x] 19.1 `uv run pytest && uv run ruff check .` passes
- [x] 19.2 `uv run ruff format --check .` passes
- [x] 19.3 Confirm no `print()` calls exist anywhere under `src/`
- [x] 19.4 Confirm no new runtime dependency was added to
      `pyproject.toml` — `search.py`/`snippet.py` build entirely on
      `lancedb` and `fastembed`
- [x] 19.5 Confirm nothing in `search.py` or `snippet.py` calls
      `table.add`/`update`/`delete`/`create_index`, or writes to the
      vault — grep for those calls to confirm absence
- [x] 19.6 Confirm every filter scenario in section 8 was verified
      against the built table's `.explain_plan()` (or equivalent) showing
      the predicate applied before the vector/FTS search, not after —
      spot-check at least one case to substantiate the pushdown claim,
      not just its externally observed row count
- [x] 19.7 Run `uv run pytest -m "not embedding"` and confirm it passes
      without requiring network access, so contributors without a cached
      model can still run the fast suite
- [x] 19.8 Update this stage's proposal/design cross-references if
      implementation surfaced a deviation (e.g. constant values chosen
      for `CANDIDATE_POOL_MULTIPLIER`/`CAP`/query-length threshold) —
      record the actual chosen values in design.md if they aren't already
      explicit there
