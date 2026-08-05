from pathlib import Path

import pytest
from eval.run import FULL_SWEEP, OVERALL_CATEGORY, EvalConfig, Query, run_eval

from vacancy_radar.index.build import build_index
from vacancy_radar.index.search import SearchMode
from vacancy_radar.index.store import IndexHandle, default_index_path, get_index_handle
from vacancy_radar.vault.reader import read_vault

FIXTURE_VAULT = Path(__file__).resolve().parent.parent / "fixtures" / "vault"
EXPECTED_OVERALL_ROW_COUNT = 2


@pytest.fixture(scope="module")
def fixture_index(tmp_path_factory: pytest.TempPathFactory) -> IndexHandle:
    vault_root = tmp_path_factory.mktemp("eval-run-fixture-vault-root")
    index_path = default_index_path(vault_root)
    build_index(read_vault(FIXTURE_VAULT), index_path)
    return get_index_handle(vault_root)


_SMALL_QUERIES = [
    Query(
        id="q-clickhouse",
        query="ClickHouse",
        expected_doc_ids=["search-fixture-terms-doc1"],
        category="technical",
        note="rare term",
    ),
    Query(
        id="q-postgresql",
        query="PostgreSQL",
        expected_doc_ids=["search-fixture-terms-doc2"],
        category="technical",
        note="adjacent term",
    ),
    Query(
        id="q-negative",
        query="sourdough bread starter troubleshooting",
        expected_doc_ids=[],
        category="negative",
        note="unrelated",
    ),
]


def test_full_sweep_produces_one_row_per_combination(
    fixture_index: IndexHandle,
) -> None:
    report = run_eval(_SMALL_QUERIES, fixture_index, FULL_SWEEP)

    overall_rows = [r for r in report.rows if r.category == OVERALL_CATEGORY]
    assert len(overall_rows) == len(FULL_SWEEP)

    categories_present = {q.category for q in _SMALL_QUERIES}
    category_rows = [r for r in report.rows if r.category != OVERALL_CATEGORY]
    for config in FULL_SWEEP:
        rows_for_config = {r.category for r in category_rows if r.config == config}
        assert rows_for_config == categories_present


def test_keyword_rows_do_not_vary_with_vector_weight(
    fixture_index: IndexHandle,
) -> None:
    configs = [
        EvalConfig(mode=SearchMode.KEYWORD, vector_weight=0.3),
        EvalConfig(mode=SearchMode.KEYWORD, vector_weight=0.7),
    ]
    report = run_eval(_SMALL_QUERIES, fixture_index, configs)
    overall = [r for r in report.rows if r.category == OVERALL_CATEGORY]

    assert len(overall) == EXPECTED_OVERALL_ROW_COUNT
    assert overall[0].recall_at_5 == overall[1].recall_at_5
    assert overall[0].mrr == overall[1].mrr


def test_semantic_rows_do_not_vary_with_vector_weight(
    fixture_index: IndexHandle,
) -> None:
    configs = [
        EvalConfig(mode=SearchMode.SEMANTIC, vector_weight=0.3),
        EvalConfig(mode=SearchMode.SEMANTIC, vector_weight=0.7),
    ]
    report = run_eval(_SMALL_QUERIES, fixture_index, configs)
    overall = [r for r in report.rows if r.category == OVERALL_CATEGORY]

    assert len(overall) == EXPECTED_OVERALL_ROW_COUNT
    assert overall[0].recall_at_5 == overall[1].recall_at_5
    assert overall[0].mrr == overall[1].mrr


def test_run_eval_is_deterministic_across_repeated_calls(
    fixture_index: IndexHandle,
) -> None:
    configs = [
        EvalConfig(mode=SearchMode.KEYWORD),
        EvalConfig(mode=SearchMode.SEMANTIC),
    ]

    first = run_eval(_SMALL_QUERIES, fixture_index, configs)
    second = run_eval(_SMALL_QUERIES, fixture_index, configs)

    assert first.rows == second.rows


def test_per_category_rows_reconcile_with_the_overall_row(
    fixture_index: IndexHandle,
) -> None:
    configs = [EvalConfig(mode=SearchMode.KEYWORD)]
    report = run_eval(_SMALL_QUERIES, fixture_index, configs)

    overall = next(r for r in report.rows if r.category == OVERALL_CATEGORY)
    category_rows = [r for r in report.rows if r.category != OVERALL_CATEGORY]

    total = sum(r.n_queries for r in category_rows)
    weighted_recall = sum(r.recall_at_5 * r.n_queries for r in category_rows) / total
    weighted_mrr = sum(r.mrr * r.n_queries for r in category_rows) / total

    assert total == overall.n_queries
    assert weighted_recall == pytest.approx(overall.recall_at_5)
    assert weighted_mrr == pytest.approx(overall.mrr)


def test_to_markdown_produces_a_well_formed_table(
    fixture_index: IndexHandle,
) -> None:
    configs = [
        EvalConfig(mode=SearchMode.KEYWORD),
        EvalConfig(mode=SearchMode.SEMANTIC),
    ]
    report = run_eval(_SMALL_QUERIES, fixture_index, configs)

    markdown = report.to_markdown()

    lines = markdown.splitlines()
    assert lines[0].startswith("|")
    assert len(lines) >= 1 + len(report.rows)
    # per-category breakdown is present, not only overall figures
    assert any("technical" in line for line in lines)
    assert any(OVERALL_CATEGORY in line for line in lines)
