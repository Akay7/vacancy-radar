import re
from pathlib import Path

import pytest
from eval.run import ALLOWED_FILTER_KEYS, Query, load_queries

from vacancy_radar.index.build import TABLE_NAME, build_index
from vacancy_radar.index.store import IndexHandle, default_index_path, get_index_handle
from vacancy_radar.vault.reader import read_vault

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
FIXTURE_VAULT = _FIXTURES_DIR / "vault"
QUERIES_PATH = Path(__file__).resolve().parent.parent.parent / "eval" / "queries.yaml"

TARGET_COUNTS = {
    "exact_name": 5,
    "technical": 5,
    "paraphrase": 4,
    "temporal": 4,
    "multi_result": 4,
    "filtered": 4,
    "negative": 4,
}

_WORD_RE = re.compile(r"[A-Za-z']+")
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "in",
    "on",
    "at",
    "to",
    "of",
    "for",
    "with",
    "each",
    "other",
    "their",
    "how",
    "did",
    "do",
    "when",
    "during",
    "throughout",
    "many",
}


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)} - _STOPWORDS


@pytest.fixture(scope="module")
def queries() -> list[Query]:
    return load_queries(QUERIES_PATH)


@pytest.fixture(scope="module")
def fixture_index(tmp_path_factory: pytest.TempPathFactory) -> IndexHandle:
    vault_root = tmp_path_factory.mktemp("eval-queries-fixture-vault-root")
    index_path = default_index_path(vault_root)
    build_index(read_vault(FIXTURE_VAULT), index_path)
    return get_index_handle(vault_root)


@pytest.fixture(scope="module")
def fixture_doc_ids(fixture_index: IndexHandle) -> set[str]:
    table = fixture_index.connection.open_table(TABLE_NAME)
    rows = table.search().select(["doc_id"]).to_arrow().to_pylist()
    return {row["doc_id"] for row in rows}


@pytest.fixture(scope="module")
def fixture_doc_texts(fixture_index: IndexHandle) -> dict[str, str]:
    table = fixture_index.connection.open_table(TABLE_NAME)
    rows = table.search().select(["doc_id", "text"]).to_arrow().to_pylist()
    return {row["doc_id"]: row["text"] for row in rows}


def test_queries_yaml_loads_into_30_well_formed_records(queries: list[Query]) -> None:
    assert len(queries) == 30  # noqa: PLR2004 - the query set's documented size
    for query in queries:
        assert query.id
        assert query.query
        assert query.category
        assert query.note
        assert isinstance(query.expected_doc_ids, list)


def test_each_category_meets_its_target_count(queries: list[Query]) -> None:
    counts: dict[str, int] = {}
    for query in queries:
        counts[query.category] = counts.get(query.category, 0) + 1

    for category, target in TARGET_COUNTS.items():
        assert counts.get(category, 0) >= target, (
            f"{category}: expected at least {target}, got {counts.get(category, 0)}"
        )


def test_query_ids_are_all_distinct(queries: list[Query]) -> None:
    ids = [query.id for query in queries]
    assert len(ids) == len(set(ids))


def test_every_expected_doc_id_resolves_in_the_fixture_index(
    queries: list[Query], fixture_doc_ids: set[str]
) -> None:
    missing = [
        (query.id, doc_id)
        for query in queries
        for doc_id in query.expected_doc_ids
        if doc_id not in fixture_doc_ids
    ]
    assert not missing, f"stale expected_doc_ids (query id, doc id): {missing}"


def test_only_negative_category_queries_have_empty_expected_doc_ids(
    queries: list[Query],
) -> None:
    for query in queries:
        if not query.expected_doc_ids:
            assert query.category == "negative"


def test_every_filtered_category_query_has_a_valid_filter_mapping(
    queries: list[Query],
) -> None:
    filtered_queries = [q for q in queries if q.category == "filtered"]
    assert filtered_queries
    for query in filtered_queries:
        assert query.filter
        assert set(query.filter).issubset(ALLOWED_FILTER_KEYS)


def test_paraphrase_queries_share_no_content_word_with_their_target(
    queries: list[Query], fixture_doc_texts: dict[str, str]
) -> None:
    paraphrase_queries = [q for q in queries if q.category == "paraphrase"]
    assert paraphrase_queries
    for query in paraphrase_queries:
        query_words = _content_words(query.query)
        assert query_words
        for doc_id in query.expected_doc_ids:
            target_words = _content_words(fixture_doc_texts[doc_id])
            assert target_words
            assert query_words.isdisjoint(target_words), (
                f"{query.id} shares content words with {doc_id}: "
                f"{query_words & target_words}"
            )
