"""Querying the disposable LanceDB index built by `index.build`.

Three modes over one table: `keyword` (BM25 full-text only), `semantic`
(vector similarity only, embedded with the model the index was actually
built with - never a default that might have drifted), and `hybrid`
(both paths run independently, fused by a swappable strategy - see
design.md). Every structured filter compiles to a SQL predicate pushed
into the LanceDB query, never applied by post-filtering a fetched result
set (see design.md's shrinking-top-k rationale).

Read-only: nothing here writes to the vault or to the index.
"""

import time
import warnings
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from lancedb.rerankers import LinearCombinationReranker, RRFReranker

from vacancy_radar.config import FusionStrategy, SearchConfig, resolve_search_config
from vacancy_radar.index import embed
from vacancy_radar.index.build import TABLE_NAME
from vacancy_radar.index.schema import read_embedding_model
from vacancy_radar.index.snippet import extract_snippet
from vacancy_radar.models import DocumentKind, Status

CANDIDATE_POOL_MULTIPLIER = 5
MIN_CANDIDATE_POOL = 50
CANDIDATE_POOL_CAP = 200
"""Hybrid mode's per-path overfetch depth - see design.md. Fixed
constants, not configurable: they bound worst-case latency, unlike
`SearchConfig`'s stage-5-tunable defaults."""

QUERY_LENGTH_WARNING_THRESHOLD_WORDS = 400
"""A conservative whitespace-token count, not an exact subword count -
`fastembed` exposes no stable per-model max-sequence-length field to
compute one exactly, and the model's own tokenizer already truncates
over-length input regardless; this threshold's only job is deciding
when to warn, not preventing a crash (see design.md)."""

if TYPE_CHECKING:
    from lancedb.table import Table

    from vacancy_radar.index.store import IndexHandle


class SearchMode(StrEnum):
    """Which retrieval path(s) `search` runs."""

    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class SearchError(Exception):
    """Base class for `search`'s typed errors."""


class EmptyQueryError(SearchError):
    """Raised when `search` is called with an empty or whitespace-only
    query string."""

    def __init__(self) -> None:
        super().__init__("query must not be empty or whitespace-only")


class InvalidLimitError(SearchError):
    """Raised when `search` is called with a negative `limit`."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"limit must not be negative, got {limit}")


class MissingFTSIndexError(SearchError):
    """Raised when a keyword or hybrid query runs against a table with
    no full-text index on `text`."""

    def __init__(self) -> None:
        super().__init__(
            "the table has no full-text index on 'text' - fix by running "
            "build_index (index.build.build_index) at least once against "
            "this index path, which creates it"
        )


class EmbeddingModelMismatchError(SearchError):
    """Raised when the embedding model recorded in the index disagrees
    with the model this codebase is currently configured to embed
    with - see design.md for why this must fail loudly."""

    def __init__(self, index_model: str | None, expected_model: str) -> None:
        self.index_model = index_model
        self.expected_model = expected_model
        recorded = index_model if index_model is not None else "<none recorded>"
        super().__init__(
            f"the index was built with embedding model {recorded!r}, but this "
            f"codebase is currently configured to embed with "
            f"{expected_model!r} - rebuild the index (index.build.build_index) "
            "with the current model, or restore the model this index expects"
        )


@dataclass(frozen=True)
class SearchHit:
    """One search result row, joined from the index table plus this
    stage's per-mode ranking and snippet extraction."""

    doc_id: str
    vacancy_id: str
    company: str
    company_slug: str
    role: str
    status: str
    kind: str
    path: str
    date: date
    score: float
    snippet: str
    keyword_rank: int | None
    semantic_rank: int | None


@dataclass(frozen=True)
class SearchResults:
    """The outcome of one `search` call."""

    hits: list[SearchHit]
    mode: SearchMode
    effective_vector_weight: float | None
    elapsed_ms: float
    total_candidates: int


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_predicate(
    *,
    company_slug: str | None,
    status: list[Status] | None,
    kind: list[DocumentKind] | None,
    tags: list[str] | None,
    since: date | None,
) -> str | None:
    """The `AND`-composed SQL predicate for the given filters, or `None`
    when none are given - pushed into the query via `.where(...,
    prefilter=True)`, never applied by post-filtering a fetched result
    set (see design.md)."""
    clauses: list[str] = []
    if company_slug is not None:
        clauses.append(f"company_slug = {_sql_string_literal(company_slug)}")
    if status:
        values = ", ".join(_sql_string_literal(str(s)) for s in status)
        clauses.append(f"status IN ({values})")
    if kind:
        values = ", ".join(_sql_string_literal(str(k)) for k in kind)
        clauses.append(f"kind IN ({values})")
    if tags:
        values = ", ".join(_sql_string_literal(t) for t in tags)
        clauses.append(f"array_has_any(tags, [{values}])")
    if since is not None:
        clauses.append(f"date >= {_sql_string_literal(since.isoformat())}")
    if not clauses:
        return None
    return " AND ".join(clauses)


def _ensure_fts_index(table: "Table") -> None:
    indices = table.list_indices()
    if not any(idx.index_type == "FTS" and "text" in idx.columns for idx in indices):
        raise MissingFTSIndexError


def _row_to_hit(
    row: dict,
    *,
    score: float,
    keyword_rank: int | None,
    semantic_rank: int | None,
    snippet: str,
) -> SearchHit:
    return SearchHit(
        doc_id=row["doc_id"],
        vacancy_id=row["vacancy_id"],
        company=row["company"],
        company_slug=row["company_slug"],
        role=row["role"],
        status=row["status"],
        kind=row["kind"],
        path=row["path"],
        date=date.fromisoformat(row["date"]),
        score=score,
        snippet=snippet,
        keyword_rank=keyword_rank,
        semantic_rank=semantic_rank,
    )


def _stable_sort(rows: list[dict], *, key: str, descending: bool) -> list[dict]:
    """`rows` ordered by `key` (as LanceDB already returned them), with
    `doc_id` ascending as an explicit secondary key - so two hits tied
    on `key` break the tie the same way on every call, rather than
    however LanceDB's internal ordering happens to land (see design.md/
    tasks.md's determinism requirement)."""
    return sorted(rows, key=lambda r: (-r[key] if descending else r[key], r["doc_id"]))


def _search_keyword(
    table: "Table", query: str, predicate: str | None, limit: int
) -> list[SearchHit]:
    _ensure_fts_index(table)
    q = table.search(query, query_type="fts")
    if predicate is not None:
        q = q.where(predicate, prefilter=True)
    rows = _stable_sort(q.limit(limit).to_list(), key="_score", descending=True)
    return [
        _row_to_hit(
            row,
            score=row["_score"],
            keyword_rank=i + 1,
            semantic_rank=None,
            snippet=extract_snippet(row["text"], query, has_keyword_match=True),
        )
        for i, row in enumerate(rows)
    ]


def _warn_if_query_too_long(query: str) -> None:
    word_count = len(query.split())
    if word_count > QUERY_LENGTH_WARNING_THRESHOLD_WORDS:
        warnings.warn(
            f"query is {word_count} words, over the "
            f"{QUERY_LENGTH_WARNING_THRESHOLD_WORDS}-word advisory threshold - the "
            "embedding model will truncate it internally rather than raise, but "
            "relevance beyond the truncation point is lost",
            stacklevel=2,
        )


def _resolve_query_embedding_model(table: "Table") -> str:
    """The model to embed a query with, guaranteed to be the model that
    actually built `table`'s vectors - raises before any embedding call
    if the table's recorded model disagrees with (or is absent, or)
    what this codebase is currently configured to embed with. See
    design.md for why this check exists at all."""
    index_model = read_embedding_model(table)
    expected_model = embed.DEFAULT_EMBEDDING_MODEL_NAME
    if index_model != expected_model:
        raise EmbeddingModelMismatchError(index_model, expected_model)
    return expected_model


def _search_semantic(
    table: "Table", query: str, predicate: str | None, limit: int, model_name: str
) -> list[SearchHit]:
    _warn_if_query_too_long(query)
    vector = embed.embed_texts([query], model_name=model_name)[0]
    q = table.search(vector, query_type="vector").distance_type("cosine")
    if predicate is not None:
        q = q.where(predicate, prefilter=True)
    rows = _stable_sort(q.limit(limit).to_list(), key="_distance", descending=False)
    return [
        _row_to_hit(
            row,
            score=1 - row["_distance"],
            keyword_rank=None,
            semantic_rank=i + 1,
            snippet=extract_snippet(row["text"], query, has_keyword_match=False),
        )
        for i, row in enumerate(rows)
    ]


def _candidate_pool_size(limit: int) -> int:
    """How many candidates each of hybrid's two paths fetches on its
    own, before fusion - enough overlap for fusion to work with,
    bounded so worst-case latency stays predictable (see design.md)."""
    depth = limit * CANDIDATE_POOL_MULTIPLIER
    return min(max(depth, MIN_CANDIDATE_POOL), CANDIDATE_POOL_CAP)


def _search_hybrid(  # noqa: PLR0913, PLR0917 - internal; each arg is load-bearing
    table: "Table",
    query: str,
    predicate: str | None,
    limit: int,
    model_name: str,
    config: SearchConfig,
    vector_weight_arg: float | None,
) -> tuple[list[SearchHit], int, float | None]:
    """Run the keyword and semantic paths independently (each its own
    LanceDB query, so each path's own rank is directly observable),
    then fuse with LanceDB's own tested reranker classes - RRF by
    default, Linear Combination as the config-selected alternative.
    See design.md for why this isn't `table.search(..., query_type="hybrid")`.
    """
    _warn_if_query_too_long(query)
    pool_size = _candidate_pool_size(limit)

    fts_q = table.search(query, query_type="fts").with_row_id(with_row_id=True)
    if predicate is not None:
        fts_q = fts_q.where(predicate, prefilter=True)
    fts_table = fts_q.limit(pool_size).to_arrow()

    vector = embed.embed_texts([query], model_name=model_name)[0]
    vector_q = (
        table.search(vector, query_type="vector")
        .distance_type("cosine")
        .with_row_id(with_row_id=True)
    )
    if predicate is not None:
        vector_q = vector_q.where(predicate, prefilter=True)
    vector_table = vector_q.limit(pool_size).to_arrow()

    keyword_ranks = {
        row["doc_id"]: i + 1 for i, row in enumerate(fts_table.to_pylist())
    }
    semantic_ranks = {
        row["doc_id"]: i + 1 for i, row in enumerate(vector_table.to_pylist())
    }
    total_candidates = len(set(keyword_ranks) | set(semantic_ranks))

    effective_vector_weight: float | None = None
    if config.fusion_strategy is FusionStrategy.RRF:
        reranker = RRFReranker()
    else:
        effective_vector_weight = (
            vector_weight_arg
            if vector_weight_arg is not None
            else config.default_vector_weight
        )
        reranker = LinearCombinationReranker(weight=effective_vector_weight)

    fused = reranker.rerank_hybrid(query, vector_table, fts_table).to_pylist()
    fused = _stable_sort(fused, key="_relevance_score", descending=True)[:limit]

    hits = [
        _row_to_hit(
            row,
            score=row["_relevance_score"],
            keyword_rank=keyword_ranks.get(row["doc_id"]),
            semantic_rank=semantic_ranks.get(row["doc_id"]),
            snippet=extract_snippet(
                row["text"], query, has_keyword_match=row["doc_id"] in keyword_ranks
            ),
        )
        for row in fused
    ]
    return hits, total_candidates, effective_vector_weight


def _empty_results(mode: SearchMode, elapsed_ms: float) -> SearchResults:
    return SearchResults(
        hits=[],
        mode=mode,
        effective_vector_weight=None,
        elapsed_ms=elapsed_ms,
        total_candidates=0,
    )


def search(  # noqa: PLR0913 - the deliverable's public signature; each is meaningful
    index: "IndexHandle",
    query: str,
    *,
    mode: SearchMode | None = None,
    company_slug: str | None = None,
    status: list[Status] | None = None,
    kind: list[DocumentKind] | None = None,
    tags: list[str] | None = None,
    since: date | None = None,
    limit: int | None = None,
    vector_weight: float | None = None,
) -> SearchResults:
    """Search `index`'s table.

    `mode`, `limit`, and `vector_weight` default to `None`, resolving
    against `resolve_search_config()` at call time rather than a literal
    Python default - see design.md for why (stage 5 must be able to
    retune these without editing this function). An explicit argument
    always overrides the configured default for that one call.
    """
    if not query.strip():
        raise EmptyQueryError

    config = resolve_search_config()
    effective_mode = mode if mode is not None else SearchMode(config.default_mode)
    effective_limit = limit if limit is not None else config.default_limit

    if effective_limit < 0:
        raise InvalidLimitError(effective_limit)

    start = time.perf_counter()

    if effective_limit == 0:
        return _empty_results(effective_mode, (time.perf_counter() - start) * 1000)

    predicate = _build_predicate(
        company_slug=company_slug, status=status, kind=kind, tags=tags, since=since
    )
    table = index.connection.open_table(TABLE_NAME)

    effective_vector_weight: float | None = None
    if effective_mode is SearchMode.KEYWORD:
        hits = _search_keyword(table, query, predicate, effective_limit)
        total_candidates = len(hits)
    elif effective_mode is SearchMode.SEMANTIC:
        model_name = _resolve_query_embedding_model(table)
        hits = _search_semantic(table, query, predicate, effective_limit, model_name)
        total_candidates = len(hits)
    else:
        model_name = _resolve_query_embedding_model(table)
        hits, total_candidates, effective_vector_weight = _search_hybrid(
            table, query, predicate, effective_limit, model_name, config, vector_weight
        )

    elapsed_ms = (time.perf_counter() - start) * 1000
    return SearchResults(
        hits=hits,
        mode=effective_mode,
        effective_vector_weight=effective_vector_weight,
        elapsed_ms=elapsed_ms,
        total_candidates=total_candidates,
    )
