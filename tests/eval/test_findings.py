"""The three directional claims the project makes about its own
retrieval design (see specs/eval-runner/spec.md and design.md) -
checked against the full sweep, run once per test session and shared
via a module-scoped fixture since it's the slow part.

These assert *direction*, not a threshold: if the fixture corpus ever
changes in a way that flips one of them, that's a real regression this
suite is meant to catch, not a test to loosen (see design.md's Risks).
"""

from pathlib import Path

import pytest
from eval.run import FULL_SWEEP, OVERALL_CATEGORY, EvalReport, load_queries, run_eval

from vacancy_radar.index.build import build_index
from vacancy_radar.index.search import SearchMode
from vacancy_radar.index.store import IndexHandle, default_index_path, get_index_handle
from vacancy_radar.vault.reader import read_vault

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_VAULT = _REPO_ROOT / "tests" / "fixtures" / "vault"
QUERIES_PATH = _REPO_ROOT / "eval" / "queries.yaml"


@pytest.fixture(scope="module")
def fixture_index(tmp_path_factory: pytest.TempPathFactory) -> IndexHandle:
    vault_root = tmp_path_factory.mktemp("eval-findings-fixture-vault-root")
    index_path = default_index_path(vault_root)
    build_index(read_vault(FIXTURE_VAULT), index_path)
    return get_index_handle(vault_root)


@pytest.fixture(scope="module")
def full_report(fixture_index: IndexHandle) -> EvalReport:
    queries = load_queries(QUERIES_PATH)
    return run_eval(queries, fixture_index, FULL_SWEEP)


def _row(report: EvalReport, *, mode: SearchMode, category: str) -> float:
    matches = [
        r for r in report.rows if r.config.mode is mode and r.category == category
    ]
    assert len(matches) == 1, f"expected one {mode}/{category} row, got {matches}"
    return matches[0].recall_at_5


def test_exact_name_recall_is_at_least_as_high_under_keyword_as_semantic(
    full_report: EvalReport,
) -> None:
    keyword_recall = _row(full_report, mode=SearchMode.KEYWORD, category="exact_name")
    semantic_recall = _row(full_report, mode=SearchMode.SEMANTIC, category="exact_name")

    assert keyword_recall >= semantic_recall


def test_paraphrase_recall_is_strictly_higher_under_semantic_than_keyword(
    full_report: EvalReport,
) -> None:
    keyword_recall = _row(full_report, mode=SearchMode.KEYWORD, category="paraphrase")
    semantic_recall = _row(full_report, mode=SearchMode.SEMANTIC, category="paraphrase")

    assert semantic_recall > keyword_recall


def test_the_best_hybrid_config_is_at_least_as_good_as_the_better_single_mode_overall(
    full_report: EvalReport,
) -> None:
    keyword_overall = _row(
        full_report, mode=SearchMode.KEYWORD, category=OVERALL_CATEGORY
    )
    semantic_overall = _row(
        full_report, mode=SearchMode.SEMANTIC, category=OVERALL_CATEGORY
    )
    hybrid_overall_rows = [
        r
        for r in full_report.rows
        if r.config.mode is SearchMode.HYBRID and r.category == OVERALL_CATEGORY
    ]
    assert hybrid_overall_rows
    best_hybrid_recall = max(r.recall_at_5 for r in hybrid_overall_rows)

    assert best_hybrid_recall >= max(keyword_overall, semantic_overall)
