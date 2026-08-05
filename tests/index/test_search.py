import sys
from datetime import date
from pathlib import Path

import lancedb
import pytest

from vacancy_radar import frontmatter
from vacancy_radar.config import SearchConfig
from vacancy_radar.index.build import TABLE_NAME, build_index
from vacancy_radar.index.embed import DEFAULT_EMBEDDING_MODEL_NAME, vector_dim
from vacancy_radar.index.schema import build_schema
from vacancy_radar.index.search import (
    EmbeddingModelMismatchError,
    EmptyQueryError,
    InvalidLimitError,
    MissingFTSIndexError,
    SearchHit,
    SearchMode,
    SearchResults,
    _build_predicate,
    search,
)
from vacancy_radar.index.store import IndexHandle, default_index_path, get_index_handle
from vacancy_radar.models import Document, DocumentKind, Status, Vacancy
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import read_vault

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

FIXTURE_VAULT = _FIXTURES_DIR / "vault"


def _index_handle(tmp_path: Path) -> IndexHandle:
    return get_index_handle(tmp_path)


_TIE_TEXT = (
    "Identical note text shared by two documents on purpose, for tie-break tests."
)
_TIE_DOC_ID_LOW = "tie-vacancy-doc1"
_TIE_DOC_ID_HIGH = "tie-vacancy-doc2"


def _tie_vault(tmp_path: Path) -> Path:
    """A minimal vault with two documents whose bodies are byte-
    identical - guarantees a real BM25 tie (equal term frequencies,
    equal doc length) and a real semantic tie (fastembed is
    deterministic: identical input text produces bit-identical
    vectors), so ordering between them is genuinely undetermined by
    relevance and must fall back to the documented doc_id tie-break."""
    vault = tmp_path / "tie-vault"
    (vault / VAULT_MARKER_DIRNAME).mkdir(parents=True)
    company_dir = vault / "tie-corp"
    company_dir.mkdir(parents=True)
    (company_dir / "_company.md").write_text(
        frontmatter.serialize(
            {"slug": "tie-corp", "name": "Tie Corp", "domains": ["tie-corp.example"]},
            "",
        ),
        encoding="utf-8",
    )
    vacancy = Vacancy(
        id="tie-vacancy",
        company="Tie Corp",
        company_slug="tie-corp",
        role="Engineer",
        source_url="https://jobs.tie-corp.example/tie-vacancy",
        status=Status.FOUND,
        found_date=date(2026, 1, 1),
    )
    vacancy_dir = company_dir / "tie-vacancy"
    vacancy_dir.mkdir()
    metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    (vacancy_dir / "vacancy.md").write_text(
        frontmatter.serialize(metadata, "# Engineer\n"), encoding="utf-8"
    )
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir()
    for doc_id in (_TIE_DOC_ID_LOW, _TIE_DOC_ID_HIGH):
        document = Document(
            id=doc_id,
            vacancy_id="tie-vacancy",
            kind=DocumentKind.NOTE,
            title="Tie note",
            date=date(2026, 1, 2),
        )
        doc_metadata = document.model_dump(mode="json", exclude_none=True)
        (docs_dir / f"{doc_id}.md").write_text(
            frontmatter.serialize(doc_metadata, _TIE_TEXT), encoding="utf-8"
        )
    return vault


@pytest.fixture(scope="module")
def fixture_index(tmp_path_factory: pytest.TempPathFactory) -> IndexHandle:
    """The committed fixture vault, built once and reused read-only by
    every test in this module - building is the slow, embedding-marked
    part; querying it is what's actually under test."""
    vault_root = tmp_path_factory.mktemp("search-fixture-vault-root")
    index_path = default_index_path(vault_root)
    build_index(read_vault(FIXTURE_VAULT), index_path)
    return get_index_handle(vault_root)


# --- Section 6: module skeleton ---------------------------------------------


def test_search_mode_has_exactly_the_three_documented_members() -> None:
    assert {m.value for m in SearchMode} == {"keyword", "semantic", "hybrid"}


def test_importing_search_and_config_together_does_not_raise() -> None:
    import vacancy_radar.config  # noqa: PLC0415
    import vacancy_radar.index.search  # noqa: PLC0415

    assert vacancy_radar.config is not None
    assert vacancy_radar.index.search is not None


def test_config_valid_search_modes_matches_search_mode_members() -> None:
    """config.py can't import search.py (see config.py's docstring), so
    it keeps its own mirror of SearchMode's values - this test is the
    guard against the two drifting apart silently."""
    from vacancy_radar.config import _VALID_SEARCH_MODES  # noqa: PLC0415

    assert {m.value for m in SearchMode} == _VALID_SEARCH_MODES


def test_search_config_default_mode_is_a_valid_search_mode() -> None:
    assert SearchMode(SearchConfig().default_mode) in set(SearchMode)


def test_search_results_and_search_hit_construct_with_the_documented_fields() -> None:
    hit = SearchHit(
        doc_id="doc-1",
        vacancy_id="vac-1",
        company="Acme",
        company_slug="acme",
        role="Engineer",
        status="found",
        kind="note",
        path="/vault/acme/vac-1/documents/doc-1.md",
        date=date(2026, 1, 1),
        score=1.0,
        snippet="a snippet",
        keyword_rank=1,
        semantic_rank=None,
    )
    results = SearchResults(
        hits=[hit],
        mode=SearchMode.KEYWORD,
        effective_vector_weight=None,
        elapsed_ms=1.5,
        total_candidates=1,
    )

    assert results.hits == [hit]
    assert results.mode is SearchMode.KEYWORD
    assert results.effective_vector_weight is None
    assert results.elapsed_ms == 1.5  # noqa: PLR2004
    assert results.total_candidates == 1
    assert hit.doc_id == "doc-1"
    assert hit.keyword_rank == 1
    assert hit.semantic_rank is None


# --- Section 7: query and limit validation ----------------------------------


@pytest.mark.parametrize("mode", list(SearchMode))
@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_empty_or_whitespace_query_raises_before_touching_the_index(
    tmp_path: Path, mode: SearchMode, query: str
) -> None:
    index = _index_handle(tmp_path)

    with pytest.raises(EmptyQueryError):
        search(index, query, mode=mode)


def test_limit_zero_returns_empty_results_without_error(tmp_path: Path) -> None:
    index = _index_handle(tmp_path)

    results = search(index, "anything", mode=SearchMode.KEYWORD, limit=0)

    assert results.hits == []


def test_negative_limit_raises_invalid_limit_error(tmp_path: Path) -> None:
    index = _index_handle(tmp_path)

    with pytest.raises(InvalidLimitError):
        search(index, "anything", mode=SearchMode.KEYWORD, limit=-1)


# --- Section 8: predicate builder and filter pushdown -----------------------


def test_build_predicate_with_no_filters_returns_none() -> None:
    assert (
        _build_predicate(
            company_slug=None, status=None, kind=None, tags=None, since=None
        )
        is None
    )


def test_build_predicate_company_slug() -> None:
    predicate = _build_predicate(
        company_slug="acme", status=None, kind=None, tags=None, since=None
    )
    assert predicate == "company_slug = 'acme'"


def test_build_predicate_status_in() -> None:
    predicate = _build_predicate(
        company_slug=None,
        status=[Status.FOUND, Status.APPLIED],
        kind=None,
        tags=None,
        since=None,
    )
    assert predicate == "status IN ('found', 'applied')"


def test_build_predicate_kind_in() -> None:
    predicate = _build_predicate(
        company_slug=None,
        status=None,
        kind=[DocumentKind.NOTE, DocumentKind.EMAIL],
        tags=None,
        since=None,
    )
    assert predicate == "kind IN ('note', 'email')"


def test_build_predicate_tags_array_has_any() -> None:
    predicate = _build_predicate(
        company_slug=None, status=None, kind=None, tags=["urgent", "remote"], since=None
    )
    assert predicate == "array_has_any(tags, ['urgent', 'remote'])"


def test_build_predicate_since() -> None:
    predicate = _build_predicate(
        company_slug=None,
        status=None,
        kind=None,
        tags=None,
        since=date(2026, 1, 1),
    )
    assert predicate == "date >= '2026-01-01'"


def test_build_predicate_combines_with_and() -> None:
    predicate = _build_predicate(
        company_slug="acme",
        status=[Status.FOUND],
        kind=None,
        tags=None,
        since=None,
    )
    assert predicate == "company_slug = 'acme' AND status IN ('found')"


@pytest.mark.embedding
def test_company_slug_restricts_results_and_excludes_other_companies(
    fixture_index: IndexHandle,
) -> None:
    broad = search(fixture_index, "Engineer", mode=SearchMode.KEYWORD, limit=100)
    slugs_present = {h.company_slug for h in broad.hits}
    assert len(slugs_present) >= 2  # noqa: PLR2004 - need at least two to prove exclusion

    target, other = sorted(slugs_present)[:2]
    filtered = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        company_slug=target,
        limit=100,
    )

    assert filtered.hits
    assert {h.company_slug for h in filtered.hits} == {target}
    assert not any(h.company_slug == other for h in filtered.hits)


@pytest.mark.embedding
def test_status_filter_returns_union_of_given_statuses(
    fixture_index: IndexHandle,
) -> None:
    broad = search(fixture_index, "Engineer", mode=SearchMode.KEYWORD, limit=200)
    statuses_present = {h.status for h in broad.hits}
    assert len(statuses_present) >= 2  # noqa: PLR2004 - need at least two to prove union

    chosen = sorted(statuses_present)[:2]
    filtered = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        status=[Status(s) for s in chosen],
        limit=200,
    )

    assert filtered.hits
    assert {h.status for h in filtered.hits} <= set(chosen)
    assert set(chosen) == {h.status for h in filtered.hits}


@pytest.mark.embedding
def test_kind_filter_restricts_to_given_kinds(fixture_index: IndexHandle) -> None:
    filtered = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        kind=[DocumentKind.NOTE],
        limit=200,
    )

    assert filtered.hits
    assert {h.kind for h in filtered.hits} == {DocumentKind.NOTE.value}


@pytest.mark.embedding
def test_tags_filter_restricts_to_documents_carrying_the_tag(
    fixture_index: IndexHandle,
) -> None:
    # "needs_review" is only ever applied to unknown-role vacancies (see
    # generate.py), whose composed text and document bodies substitute
    # the literal role placeholder "unknown" - not "Engineer".
    filtered = search(
        fixture_index,
        "unknown",
        mode=SearchMode.KEYWORD,
        tags=["needs_review"],
        limit=200,
    )

    assert filtered.hits
    snapshot = read_vault(FIXTURE_VAULT)
    for hit in filtered.hits:
        assert "needs_review" in snapshot.vacancies[hit.vacancy_id].tags


@pytest.mark.embedding
def test_since_filter_excludes_earlier_dated_documents(
    fixture_index: IndexHandle,
) -> None:
    broad = search(fixture_index, "Engineer", mode=SearchMode.KEYWORD, limit=200)
    dates_present = sorted({h.date for h in broad.hits})
    assert len(dates_present) >= 2  # noqa: PLR2004 - need spread to prove exclusion
    cutoff = dates_present[len(dates_present) // 2]

    filtered = search(
        fixture_index, "Engineer", mode=SearchMode.KEYWORD, since=cutoff, limit=200
    )

    assert filtered.hits
    assert all(h.date >= cutoff for h in filtered.hits)
    assert len(filtered.hits) < len(broad.hits)


@pytest.mark.embedding
def test_combined_filters_compose_as_and(fixture_index: IndexHandle) -> None:
    broad = search(fixture_index, "Engineer", mode=SearchMode.KEYWORD, limit=200)
    by_slug: dict[str, set[str]] = {}
    for hit in broad.hits:
        by_slug.setdefault(hit.company_slug, set()).add(hit.status)

    target_slug, target_status = next(
        (slug, next(iter(statuses))) for slug, statuses in by_slug.items()
    )
    other_status = next(
        (s for statuses in by_slug.values() for s in statuses if s != target_status),
        None,
    )
    assert other_status is not None

    filtered = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        company_slug=target_slug,
        status=[Status(target_status)],
        limit=200,
    )

    assert filtered.hits
    assert all(
        h.company_slug == target_slug and h.status == target_status
        for h in filtered.hits
    )
    assert not any(
        h.company_slug == target_slug and h.status == other_status
        for h in filtered.hits
    )


@pytest.mark.embedding
def test_impossible_filter_combination_returns_empty(
    fixture_index: IndexHandle,
) -> None:
    results = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        company_slug="does-not-exist-anywhere",
        limit=10,
    )

    assert results.hits == []


@pytest.mark.embedding
def test_filter_with_enough_matches_still_fills_the_limit(
    fixture_index: IndexHandle,
) -> None:
    small_limit = 3
    broad = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        kind=[DocumentKind.NOTE, DocumentKind.EMAIL, DocumentKind.POSTING],
        limit=200,
    )
    assert len(broad.hits) > small_limit

    limited = search(
        fixture_index,
        "Engineer",
        mode=SearchMode.KEYWORD,
        kind=[DocumentKind.NOTE, DocumentKind.EMAIL, DocumentKind.POSTING],
        limit=small_limit,
    )

    assert len(limited.hits) == small_limit


# --- Section 9: FTS-index-presence guard ------------------------------------


@pytest.mark.embedding
def test_no_fts_index_raises_missing_fts_index_error_naming_the_fix(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    (vault / ".vacancy-radar").mkdir(parents=True)
    index_path = default_index_path(vault)
    build_index(read_vault(FIXTURE_VAULT), index_path)

    # Drop the FTS index build_index just created, leaving the table
    # otherwise intact - the guard must catch this before querying.
    table = lancedb.connect(index_path).open_table(TABLE_NAME)
    for idx in table.list_indices():
        table.drop_index(idx.name)

    index = get_index_handle(vault)
    with pytest.raises(MissingFTSIndexError, match="build_index"):
        search(index, "Engineer", mode=SearchMode.KEYWORD)


# --- Section 10: keyword mode ------------------------------------------------


@pytest.mark.embedding
def test_exact_company_name_returns_that_companys_documents(
    fixture_index: IndexHandle,
) -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    vacancy = next(iter(snapshot.vacancies.values()))

    results = search(fixture_index, vacancy.company, mode=SearchMode.KEYWORD, limit=50)

    assert results.hits
    assert any(h.company_slug == vacancy.company_slug for h in results.hits)


@pytest.mark.embedding
def test_distinctive_proper_noun_ranks_its_sole_document_first(
    fixture_index: IndexHandle,
) -> None:
    from generate import DISTINCTIVE_PROPER_NOUN  # noqa: PLC0415

    results = search(
        fixture_index, DISTINCTIVE_PROPER_NOUN, mode=SearchMode.KEYWORD, limit=10
    )

    assert results.hits
    assert results.hits[0].doc_id == "search-fixture-terms-doc3"


@pytest.mark.embedding
def test_rare_term_excludes_adjacent_topic_document(
    fixture_index: IndexHandle,
) -> None:
    from generate import RARE_TECH_TERM  # noqa: PLC0415

    results = search(fixture_index, RARE_TECH_TERM, mode=SearchMode.KEYWORD, limit=10)

    hit_ids = {h.doc_id for h in results.hits}
    assert "search-fixture-terms-doc1" in hit_ids
    assert "search-fixture-terms-doc2" not in hit_ids


@pytest.mark.embedding
def test_query_matching_nothing_returns_empty_not_an_error(
    fixture_index: IndexHandle,
) -> None:
    results = search(fixture_index, "zzznonexistenttermzzz", mode=SearchMode.KEYWORD)

    assert results.hits == []


@pytest.mark.embedding
def test_keyword_scores_are_non_increasing(fixture_index: IndexHandle) -> None:
    results = search(fixture_index, "Engineer", mode=SearchMode.KEYWORD, limit=50)

    scores = [h.score for h in results.hits]
    assert len(scores) > 1
    assert scores == sorted(scores, reverse=True)


@pytest.mark.embedding
def test_keyword_mode_never_loads_the_embedding_model(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vacancy_radar.index import embed  # noqa: PLC0415

    def _fail(*_args: object, **_kwargs: object) -> None:
        msg = "keyword mode must never load the embedding model"
        raise AssertionError(msg)

    monkeypatch.setattr(embed, "_get_model", _fail)

    results = search(fixture_index, "Engineer", mode=SearchMode.KEYWORD, limit=5)

    assert results.hits


# --- Section 11: embedding-model resolution and mismatch guard --------------


@pytest.mark.embedding
def test_query_embedded_with_recorded_model_when_it_matches_default(
    fixture_index: IndexHandle,
) -> None:
    results = search(fixture_index, "Engineer", mode=SearchMode.SEMANTIC, limit=5)

    assert results.hits


@pytest.mark.embedding
@pytest.mark.parametrize("mode", [SearchMode.SEMANTIC, SearchMode.HYBRID])
def test_mismatched_recorded_model_raises_before_embedding(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch, mode: SearchMode
) -> None:
    from vacancy_radar.index import embed  # noqa: PLC0415

    monkeypatch.setattr(embed, "DEFAULT_EMBEDDING_MODEL_NAME", "some/other-model")

    def _fail(*_args: object, **_kwargs: object) -> None:
        msg = "must not embed on a model mismatch"
        raise AssertionError(msg)

    monkeypatch.setattr(embed, "_get_model", _fail)

    with pytest.raises(EmbeddingModelMismatchError) as exc_info:
        search(fixture_index, "Engineer", mode=mode)

    assert DEFAULT_EMBEDDING_MODEL_NAME in str(exc_info.value)
    assert "some/other-model" in str(exc_info.value)


@pytest.mark.embedding
@pytest.mark.parametrize("mode", [SearchMode.SEMANTIC, SearchMode.HYBRID])
def test_no_recorded_model_raises_the_same_typed_error(
    tmp_path: Path, mode: SearchMode
) -> None:
    dim = vector_dim(DEFAULT_EMBEDDING_MODEL_NAME)
    vault = tmp_path / "vault"
    (vault / ".vacancy-radar").mkdir(parents=True)
    index_path = default_index_path(vault)
    db = lancedb.connect(index_path)
    db.create_table(TABLE_NAME, schema=build_schema(dim))  # no model metadata

    index = get_index_handle(vault)
    with pytest.raises(EmbeddingModelMismatchError):
        search(index, "Engineer", mode=mode)


# --- Section 12: semantic mode -----------------------------------------------


@pytest.mark.embedding
def test_paraphrase_query_returns_its_target_under_semantic_mode(
    fixture_index: IndexHandle,
) -> None:
    from generate import (  # noqa: PLC0415
        SEMANTIC_PARAPHRASE_QUERY,
        SEMANTIC_PARAPHRASE_TARGET_DOC_ID,
    )

    results = search(
        fixture_index, SEMANTIC_PARAPHRASE_QUERY, mode=SearchMode.SEMANTIC, limit=10
    )

    assert any(h.doc_id == SEMANTIC_PARAPHRASE_TARGET_DOC_ID for h in results.hits)


@pytest.mark.embedding
def test_same_paraphrase_query_does_not_return_target_under_keyword_mode(
    fixture_index: IndexHandle,
) -> None:
    from generate import (  # noqa: PLC0415
        SEMANTIC_PARAPHRASE_QUERY,
        SEMANTIC_PARAPHRASE_TARGET_DOC_ID,
    )

    results = search(
        fixture_index, SEMANTIC_PARAPHRASE_QUERY, mode=SearchMode.KEYWORD, limit=50
    )

    assert not any(h.doc_id == SEMANTIC_PARAPHRASE_TARGET_DOC_ID for h in results.hits)


@pytest.mark.embedding
def test_semantic_scores_are_non_increasing(fixture_index: IndexHandle) -> None:
    results = search(fixture_index, "Engineer", mode=SearchMode.SEMANTIC, limit=50)

    scores = [h.score for h in results.hits]
    assert len(scores) > 1
    assert scores == sorted(scores, reverse=True)


# --- Section 13: hybrid mode - per-path ranks and fusion ---------------------

_TOP_N_OVERLAP = 5
_MIN_OVERLAP = 3

# "Engineer" alone floods the templated fixture corpus with BM25 ties
# (dozens of documents share the exact same score), which makes
# top-N-ordering comparisons meaningless - not because fusion is wrong,
# but because tie-breaking order legitimately differs between a direct
# top-k FTS query and a fetch-then-rerank pipeline. A two-term query
# graded enough to avoid ties in its top few results (confirmed
# empirically against the committed fixture) makes ordering comparisons
# actually test what they claim to.
_HYBRID_QUERY = "Engineer applying"


@pytest.mark.embedding
def test_hybrid_hits_come_from_keyword_or_semantic_candidates(
    fixture_index: IndexHandle,
) -> None:
    keyword = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.KEYWORD, limit=200)
    semantic = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.SEMANTIC, limit=200)
    hybrid = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.HYBRID, limit=20)

    allowed = {h.doc_id for h in keyword.hits} | {h.doc_id for h in semantic.hits}
    assert hybrid.hits
    assert all(h.doc_id in allowed for h in hybrid.hits)


def _fix_candidate_pool_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force hybrid's per-path pool to stay at MIN_CANDIDATE_POOL
    regardless of `limit`, so a `limit` chosen to exceed the pool's
    dual-path count (which otherwise always outranks single-path
    candidates under RRF - see design.md) doesn't also inflate the pool
    and erase the very single-path candidates the test needs to see."""
    import vacancy_radar.index.search as search_module  # noqa: PLC0415

    monkeypatch.setattr(search_module, "CANDIDATE_POOL_MULTIPLIER", 0)


@pytest.mark.embedding
def test_dual_path_hit_outranks_single_path_hit(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fix_candidate_pool_depth(monkeypatch)

    results = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.HYBRID, limit=60)

    dual_positions = [
        i
        for i, h in enumerate(results.hits)
        if h.keyword_rank is not None and h.semantic_rank is not None
    ]
    single_positions = [
        i
        for i, h in enumerate(results.hits)
        if (h.keyword_rank is None) != (h.semantic_rank is None)
    ]

    assert dual_positions
    assert single_positions
    assert min(dual_positions) < min(single_positions)


@pytest.mark.embedding
def test_hybrid_hits_report_correct_per_path_ranks(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fix_candidate_pool_depth(monkeypatch)

    pool_limit = 50  # MIN_CANDIDATE_POOL, matching the pool fixed above
    keyword = search(
        fixture_index, _HYBRID_QUERY, mode=SearchMode.KEYWORD, limit=pool_limit
    )
    semantic = search(
        fixture_index, _HYBRID_QUERY, mode=SearchMode.SEMANTIC, limit=pool_limit
    )
    keyword_ids = {h.doc_id for h in keyword.hits}
    semantic_ids = {h.doc_id for h in semantic.hits}

    hybrid = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.HYBRID, limit=60)
    assert hybrid.hits

    saw_dual = saw_single = False
    for h in hybrid.hits:
        in_keyword = h.doc_id in keyword_ids
        in_semantic = h.doc_id in semantic_ids
        assert in_keyword or in_semantic
        assert (h.keyword_rank is not None) == in_keyword
        assert (h.semantic_rank is not None) == in_semantic
        saw_dual = saw_dual or (in_keyword and in_semantic)
        saw_single = saw_single or (in_keyword != in_semantic)

    assert saw_dual
    assert saw_single


@pytest.mark.embedding
def test_vector_weight_changes_ordering_under_linear_combination(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_FUSION_STRATEGY", "linear_combination")

    low = search(
        fixture_index,
        _HYBRID_QUERY,
        mode=SearchMode.HYBRID,
        vector_weight=0.05,
        limit=20,
    )
    high = search(
        fixture_index,
        _HYBRID_QUERY,
        mode=SearchMode.HYBRID,
        vector_weight=0.95,
        limit=20,
    )

    assert [h.doc_id for h in low.hits] != [h.doc_id for h in high.hits]


@pytest.mark.embedding
def test_extreme_vector_weight_approximates_single_mode_ordering(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_FUSION_STRATEGY", "linear_combination")

    keyword = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.KEYWORD, limit=10)
    semantic = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.SEMANTIC, limit=10)
    near_keyword = search(
        fixture_index,
        _HYBRID_QUERY,
        mode=SearchMode.HYBRID,
        vector_weight=0.0,
        limit=10,
    )
    near_semantic = search(
        fixture_index,
        _HYBRID_QUERY,
        mode=SearchMode.HYBRID,
        vector_weight=1.0,
        limit=10,
    )

    keyword_top = {h.doc_id for h in keyword.hits[:_TOP_N_OVERLAP]}
    semantic_top = {h.doc_id for h in semantic.hits[:_TOP_N_OVERLAP]}
    near_keyword_top = {h.doc_id for h in near_keyword.hits[:_TOP_N_OVERLAP]}
    near_semantic_top = {h.doc_id for h in near_semantic.hits[:_TOP_N_OVERLAP]}

    assert len(keyword_top & near_keyword_top) >= _MIN_OVERLAP
    assert len(semantic_top & near_semantic_top) >= _MIN_OVERLAP


@pytest.mark.embedding
def test_effective_vector_weight_is_none_under_default_rrf_fusion(
    fixture_index: IndexHandle,
) -> None:
    results = search(
        fixture_index,
        _HYBRID_QUERY,
        mode=SearchMode.HYBRID,
        vector_weight=0.9,
        limit=10,
    )

    assert results.effective_vector_weight is None


@pytest.mark.embedding
def test_effective_vector_weight_reflects_the_resolved_weight_under_linear_combination(
    fixture_index: IndexHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEARCH_FUSION_STRATEGY", "linear_combination")

    explicit = search(
        fixture_index,
        _HYBRID_QUERY,
        mode=SearchMode.HYBRID,
        vector_weight=0.3,
        limit=10,
    )
    assert explicit.effective_vector_weight == 0.3  # noqa: PLR2004

    defaulted = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.HYBRID, limit=10)
    assert defaulted.effective_vector_weight == SearchConfig().default_vector_weight


# --- Section 14: determinism and tie-breaking --------------------------------


@pytest.mark.embedding
@pytest.mark.parametrize("mode", list(SearchMode))
def test_repeating_the_same_query_reproduces_the_same_order(
    fixture_index: IndexHandle, mode: SearchMode
) -> None:
    first = search(fixture_index, _HYBRID_QUERY, mode=mode, limit=20)
    second = search(fixture_index, _HYBRID_QUERY, mode=mode, limit=20)

    assert [h.doc_id for h in first.hits] == [h.doc_id for h in second.hits]


@pytest.mark.embedding
@pytest.mark.parametrize("mode", list(SearchMode))
def test_equal_score_hits_are_ordered_by_doc_id_ascending(
    tmp_path: Path, mode: SearchMode
) -> None:
    vault = _tie_vault(tmp_path)
    index_path = default_index_path(vault)
    build_index(read_vault(vault), index_path)
    index = get_index_handle(vault)

    query = "purpose"
    results = search(index, query, mode=mode, limit=10)

    hit_ids = [
        h.doc_id
        for h in results.hits
        if h.doc_id in (_TIE_DOC_ID_LOW, _TIE_DOC_ID_HIGH)
    ]
    assert hit_ids == [_TIE_DOC_ID_LOW, _TIE_DOC_ID_HIGH]

    # Repeat to confirm the ordering is stable, not incidentally correct once.
    again = search(index, query, mode=mode, limit=10)
    again_ids = [
        h.doc_id for h in again.hits if h.doc_id in (_TIE_DOC_ID_LOW, _TIE_DOC_ID_HIGH)
    ]
    assert again_ids == hit_ids


# --- Section 15: query-length truncation warning -----------------------------


@pytest.mark.embedding
def test_a_very_long_query_warns_and_still_returns_results(
    fixture_index: IndexHandle,
) -> None:
    from vacancy_radar.index.search import (  # noqa: PLC0415
        QUERY_LENGTH_WARNING_THRESHOLD_WORDS,
    )

    long_query = "Engineer " * (QUERY_LENGTH_WARNING_THRESHOLD_WORDS + 50)

    with pytest.warns(UserWarning, match="query"):
        results = search(fixture_index, long_query, mode=SearchMode.SEMANTIC, limit=5)

    assert results.hits


@pytest.mark.embedding
def test_a_short_query_emits_no_length_warning(fixture_index: IndexHandle) -> None:
    import warnings as warnings_module  # noqa: PLC0415

    with warnings_module.catch_warnings():
        warnings_module.simplefilter("error")
        search(fixture_index, "Engineer", mode=SearchMode.SEMANTIC, limit=5)


# --- Section 17: snippet integration -----------------------------------------


@pytest.mark.embedding
def test_a_keyword_hits_snippet_contains_the_matched_term(
    fixture_index: IndexHandle,
) -> None:
    from generate import RARE_TECH_TERM  # noqa: PLC0415

    results = search(fixture_index, RARE_TECH_TERM, mode=SearchMode.KEYWORD, limit=5)

    assert results.hits
    assert RARE_TECH_TERM.lower() in results.hits[0].snippet.lower()


@pytest.mark.embedding
def test_a_semantic_only_hits_snippet_is_the_document_opening(
    fixture_index: IndexHandle,
) -> None:
    from generate import (  # noqa: PLC0415
        SEMANTIC_PARAPHRASE_QUERY,
        SEMANTIC_PARAPHRASE_TARGET_DOC_ID,
        SEMANTIC_PARAPHRASE_TARGET_TEXT,
    )

    from vacancy_radar.index.snippet import SNIPPET_MAX_CHARS  # noqa: PLC0415

    results = search(
        fixture_index, SEMANTIC_PARAPHRASE_QUERY, mode=SearchMode.SEMANTIC, limit=10
    )

    target = next(
        h for h in results.hits if h.doc_id == SEMANTIC_PARAPHRASE_TARGET_DOC_ID
    )
    assert target.keyword_rank is None
    assert target.snippet == SEMANTIC_PARAPHRASE_TARGET_TEXT[:SNIPPET_MAX_CHARS]


@pytest.mark.embedding
def test_hit_ordering_is_unaffected_by_snippet_content(
    fixture_index: IndexHandle,
) -> None:
    """Snippet extraction runs strictly after ordering is final (see
    design.md): populating `snippet` must not disturb the score-
    descending order every mode already guarantees independently of
    snippets (tested elsewhere)."""
    results = search(fixture_index, _HYBRID_QUERY, mode=SearchMode.HYBRID, limit=20)

    assert results.hits
    assert all(isinstance(h.snippet, str) for h in results.hits)
    scores = [h.score for h in results.hits]
    assert scores == sorted(scores, reverse=True)


# --- Section 18: performance --------------------------------------------------

PERFORMANCE_TIME_BUDGET_MS = 500  # "a few hundred milliseconds"
MIN_PERFORMANCE_VACANCY_COUNT = 500


@pytest.fixture(scope="module")
def large_index(tmp_path_factory: pytest.TempPathFactory) -> IndexHandle:
    from generate import generate_vault  # noqa: PLC0415

    vault = tmp_path_factory.mktemp("search-perf-vault")
    generate_vault(vault, seed=20260101, min_companies=340, max_companies=360)
    snapshot = read_vault(vault)
    assert len(snapshot.vacancies) >= MIN_PERFORMANCE_VACANCY_COUNT
    index_path = default_index_path(vault)
    build_index(snapshot, index_path)
    return get_index_handle(vault)


@pytest.mark.embedding
@pytest.mark.parametrize("mode", list(SearchMode))
def test_search_over_a_large_index_returns_within_budget(
    large_index: IndexHandle, mode: SearchMode
) -> None:
    results = search(large_index, "Engineer", mode=mode, limit=10)

    assert results.elapsed_ms < PERFORMANCE_TIME_BUDGET_MS
