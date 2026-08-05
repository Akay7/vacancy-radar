"""The labelled query loader and the mode/weight/fusion sweep runner.

`Query` and `load_queries` read `eval/queries.yaml`'s flat records into
frozen dataclasses - see design.md for the schema rationale (no ORM, no
schema-validation library; the integrity tests in `tests/eval/
test_queries.py` are what keep the file trustworthy).

`run_eval` sweeps a `configs` sequence of `EvalConfig`s (keyword,
semantic, or hybrid at a given vector_weight/fusion_strategy) over
`queries`, scoring each with `eval.metrics.recall_at_k`/`mrr` over the
top-5 retrieved doc ids, and returns an `EvalReport` with one row per
(config, category) plus one overall-per-config rollup row. Fusion
strategy is driven via the `SEARCH_FUSION_STRATEGY` environment
variable - the only override seam `search()` exposes for it (see
design.md) - set and restored around each hybrid call, never left set
across calls.
"""

import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML

from eval.metrics import mrr as mrr_metric
from eval.metrics import recall_at_k
from vacancy_radar.config import FusionStrategy
from vacancy_radar.index.search import SearchMode, search
from vacancy_radar.models import DocumentKind, Status

if TYPE_CHECKING:
    from vacancy_radar.index.store import IndexHandle

_yaml = YAML(typ="safe")

ALLOWED_FILTER_KEYS = frozenset({"company_slug", "status", "kind", "tags", "since"})
"""Mirrors `search()`'s filter parameter names - a `filtered`-category
query's `filter` mapping may only use these keys."""

RECALL_K = 5
"""Both `recall_at_k` and `mrr` are computed over this same top-`k`
retrieved window - see design.md for why one window serves both
metrics."""

VECTOR_WEIGHTS: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7)

OVERALL_CATEGORY = "overall"
"""The sentinel `EvalRow.category` value for a config's rollup row,
alongside its per-category rows."""

_SEARCH_FUSION_STRATEGY_ENV = "SEARCH_FUSION_STRATEGY"


@dataclass(frozen=True)
class Query:
    """One labelled query from `eval/queries.yaml`."""

    id: str
    query: str
    expected_doc_ids: list[str]
    category: str
    note: str
    filter: dict[str, Any] = field(default_factory=dict)


def load_queries(path: Path) -> list[Query]:
    """Parse `path` (an `eval/queries.yaml`-shaped file) into `Query`
    records, in file order."""
    with path.open(encoding="utf-8") as fh:
        records = _yaml.load(fh)
    return [
        Query(
            id=record["id"],
            query=record["query"],
            expected_doc_ids=list(record.get("expected_doc_ids") or []),
            category=record["category"],
            note=record["note"],
            filter=dict(record.get("filter") or {}),
        )
        for record in records
    ]


@dataclass(frozen=True)
class EvalConfig:
    """One point in the mode/weight/fusion sweep.

    `vector_weight` and `fusion_strategy` are `None` and ignored for
    `keyword`/`semantic` configs - mirroring `SearchResults.
    effective_vector_weight`'s own `None`-when-inapplicable convention
    from stage 4."""

    mode: SearchMode
    vector_weight: float | None = None
    fusion_strategy: FusionStrategy | None = None


FULL_SWEEP: tuple[EvalConfig, ...] = (
    EvalConfig(mode=SearchMode.KEYWORD),
    EvalConfig(mode=SearchMode.SEMANTIC),
    *(
        EvalConfig(mode=SearchMode.HYBRID, vector_weight=weight, fusion_strategy=fusion)
        for fusion in (FusionStrategy.RRF, FusionStrategy.LINEAR_COMBINATION)
        for weight in VECTOR_WEIGHTS
    ),
)
"""keyword; semantic; hybrid at each of `VECTOR_WEIGHTS` under each
`FusionStrategy` - 12 combinations, the sweep the private `_eval` CLI
command runs by default."""


@contextmanager
def _fusion_strategy_env(strategy: FusionStrategy | None) -> Iterator[None]:
    """Set `SEARCH_FUSION_STRATEGY` to `strategy.value` for the
    duration of the block, restoring whatever the environment held
    before (or leaving it unset) on exit. A no-op when `strategy` is
    `None` - keyword/semantic configs never touch this variable."""
    if strategy is None:
        yield
        return
    previous = os.environ.get(_SEARCH_FUSION_STRATEGY_ENV)
    os.environ[_SEARCH_FUSION_STRATEGY_ENV] = strategy.value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_SEARCH_FUSION_STRATEGY_ENV, None)
        else:
            os.environ[_SEARCH_FUSION_STRATEGY_ENV] = previous


def _search_kwargs_from_filter(query_filter: dict[str, Any]) -> dict[str, Any]:
    """`search()`'s filter keyword arguments, unpacked from a `Query.
    filter` mapping - only the keys present are passed, so an absent
    filter behaves exactly like not filtering at all."""
    kwargs: dict[str, Any] = {}
    if "company_slug" in query_filter:
        kwargs["company_slug"] = query_filter["company_slug"]
    if "status" in query_filter:
        kwargs["status"] = [Status(value) for value in query_filter["status"]]
    if "kind" in query_filter:
        kwargs["kind"] = [DocumentKind(value) for value in query_filter["kind"]]
    if "tags" in query_filter:
        kwargs["tags"] = list(query_filter["tags"])
    if "since" in query_filter:
        kwargs["since"] = date.fromisoformat(query_filter["since"])
    return kwargs


def _retrieved_doc_ids(
    index: "IndexHandle", eval_query: Query, config: EvalConfig
) -> list[str]:
    fusion = config.fusion_strategy if config.mode is SearchMode.HYBRID else None
    kwargs = _search_kwargs_from_filter(eval_query.filter)
    with _fusion_strategy_env(fusion):
        results = search(
            index,
            eval_query.query,
            mode=config.mode,
            vector_weight=config.vector_weight,
            limit=RECALL_K,
            **kwargs,
        )
    return [hit.doc_id for hit in results.hits]


@dataclass(frozen=True)
class EvalRow:
    """One `(config, category)` result, or a config's `"overall"`
    rollup (see `OVERALL_CATEGORY`)."""

    config: EvalConfig
    category: str
    recall_at_5: float
    mrr: float
    n_queries: int


@dataclass(frozen=True)
class EvalReport:
    """The outcome of one `run_eval` call."""

    rows: list[EvalRow]

    def to_markdown(self) -> str:
        """Render every row as one markdown table - overall rows and
        per-category rows both, suitable for pasting into `README.md`
        or printing from the private `_eval` CLI command."""
        header = "| mode | vector_weight | fusion | category | recall@5 | MRR | n |"
        separator = "| --- | --- | --- | --- | --- | --- | --- |"
        lines = [header, separator]
        for row in self.rows:
            mode = row.config.mode.value
            weight = (
                ""
                if row.config.vector_weight is None
                else f"{row.config.vector_weight:.1f}"
            )
            strategy = row.config.fusion_strategy
            fusion = "" if strategy is None else strategy.value
            lines.append(
                f"| {mode} | {weight} | {fusion} | {row.category} | "
                f"{row.recall_at_5:.3f} | {row.mrr:.3f} | {row.n_queries} |"
            )
        return "\n".join(lines)


def run_eval(
    queries: Sequence[Query], index: "IndexHandle", configs: Sequence[EvalConfig]
) -> EvalReport:
    """Score every query in `queries` against `index` under every
    `EvalConfig` in `configs`, returning one `EvalRow` per (config,
    category) present in `queries`, plus one `OVERALL_CATEGORY` rollup
    row per config.

    Each query's `recall_at_k`/`mrr` are computed once per config (over
    a single `search()` call's top-`RECALL_K` results) and reused for
    both its category row and the overall row - so the overall row is,
    by construction, the query-count-weighted mean of the category
    rows, not a separately-computed figure that could drift from them.
    """
    rows: list[EvalRow] = []
    for config in configs:
        per_query: list[tuple[str, float, float]] = []
        for eval_query in queries:
            retrieved = _retrieved_doc_ids(index, eval_query, config)
            per_query.append(
                (
                    eval_query.category,
                    recall_at_k(eval_query.expected_doc_ids, retrieved, RECALL_K),
                    mrr_metric(eval_query.expected_doc_ids, retrieved),
                )
            )

        categories = sorted({category for category, _, _ in per_query})
        for category in categories:
            category_values = [
                (recall, query_mrr)
                for query_category, recall, query_mrr in per_query
                if query_category == category
            ]
            n = len(category_values)
            rows.append(
                EvalRow(
                    config=config,
                    category=category,
                    recall_at_5=sum(r for r, _ in category_values) / n,
                    mrr=sum(m for _, m in category_values) / n,
                    n_queries=n,
                )
            )

        rows.append(
            EvalRow(
                config=config,
                category=OVERALL_CATEGORY,
                recall_at_5=sum(r for _, r, _ in per_query) / len(per_query),
                mrr=sum(m for _, _, m in per_query) / len(per_query),
                n_queries=len(per_query),
            )
        )

    return EvalReport(rows=rows)
