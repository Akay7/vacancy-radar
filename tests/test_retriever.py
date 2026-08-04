from pathlib import Path

import pytest
from _fakes import BagOfWordsEmbedder

from vacancy_radar import ingest
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.retriever import DUPLICATE_SIMILARITY, MIN_SIMILARITY, Retriever

EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "example"
VACANCIES_DIR = EXAMPLE_DIR / "vacancies"

ACME_POSTING = (
    VACANCIES_DIR / "2026-01-15_acme-corp_backend-engineer" / "sources" / "posting.md"
).read_text()
GLOBEX_POSTING = (
    VACANCIES_DIR / "2026-02-03_globex_platform-engineer" / "sources" / "posting.md"
).read_text()

UNRELATED_JD = "Seeking an experienced pastry chef for a Michelin-starred restaurant kitchen."


@pytest.fixture
def embedder():
    return BagOfWordsEmbedder()


@pytest.fixture
def populated_store(tmp_path, embedder):
    store = ChromaStore(str(tmp_path / "chroma"))
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)
    return store


@pytest.fixture
def retriever(populated_store, embedder):
    return Retriever(store=populated_store, embedder=embedder)


# --- User Story 1: ranked similar vacancies with outcomes -------------------------------


def test_near_duplicate_jd_returns_matching_vacancy_first(retriever):
    matches = retriever.query_similar_vacancies(ACME_POSTING)
    assert matches[0].vacancy_id == "2026-01-15_acme-corp_backend-engineer"
    assert matches[0].company == "Acme Corp"
    assert matches[0].position == "Backend Engineer"
    assert matches[0].outcome == "applied"
    assert matches[0].similarity > 0.9


def test_only_posting_chunks_are_compared(populated_store, embedder):
    # vacancy.yaml's rendered text (doc_type=vacancy_meta) is distinct from posting text;
    # querying with content that only matches the correspondence email should not surface a
    # match purely from that unrelated doc_type.
    correspondence_text = (
        VACANCIES_DIR / "2026-01-15_acme-corp_backend-engineer" / "correspondence"
        / "recruiter-email.md"
    ).read_text()
    retriever = Retriever(store=populated_store, embedder=embedder)
    matches = retriever.query_similar_vacancies(correspondence_text)
    # correspondence text shares little vocabulary with the posting text, so with doc_type
    # filtering restricted to "posting" this should not surface a strong false match
    for match in matches:
        assert match.similarity < DUPLICATE_SIMILARITY


def test_doc_type_filter_is_actually_applied_at_the_query_level(populated_store, embedder):
    # With the doc_type filter disabled, correspondence content should be directly retrievable
    # against itself — proving `doc_type` genuinely restricts the vector-store query (FR-008),
    # not just something that happens to look right from the already-filtered default.
    correspondence_text = (
        VACANCIES_DIR / "2026-01-15_acme-corp_backend-engineer" / "correspondence"
        / "recruiter-email.md"
    ).read_text()
    retriever = Retriever(store=populated_store, embedder=embedder)

    filtered = retriever.query_similar_vacancies(correspondence_text, doc_type="posting")
    unfiltered = retriever.query_similar_vacancies(correspondence_text, doc_type=None)

    assert all(m.similarity < DUPLICATE_SIMILARITY for m in filtered)
    assert any(m.similarity >= DUPLICATE_SIMILARITY for m in unfiltered)


def test_results_ordered_most_to_least_similar(retriever):
    # a JD that's a blend, closer to Acme's wording
    matches = retriever.query_similar_vacancies(ACME_POSTING + " " + GLOBEX_POSTING[:50])
    similarities = [m.similarity for m in matches]
    assert similarities == sorted(similarities, reverse=True)


# --- User Story 2: duplicate-application flag -------------------------------------------


def test_high_similarity_match_flagged_as_duplicate(retriever):
    matches = retriever.query_similar_vacancies(ACME_POSTING)
    assert matches[0].similarity >= DUPLICATE_SIMILARITY
    assert matches[0].is_duplicate is True


def test_moderate_similarity_match_not_flagged_as_duplicate(tmp_path, embedder):
    # A partial-word-overlap posting/query pair, calibrated (empirically, against
    # BagOfWordsEmbedder) to land between MIN_SIMILARITY and DUPLICATE_SIMILARITY — a
    # real "somewhat similar, not a duplicate" match, distinct from the near-identical case.
    posting = (
        "Backend Engineer position at Acme Corp building APIs with Python and PostgreSQL "
        "for high traffic services and reliable systems."
    )
    query = (
        "Backend Engineer role building services with Python for a growing technology "
        "company and reliable systems."
    )
    vacancy_dir = tmp_path / "vacancies" / "2026-09-01_other-corp_backend-engineer"
    (vacancy_dir / "sources").mkdir(parents=True)
    (vacancy_dir / "vacancy.yaml").write_text(
        "company: Other Corp\nposition: Backend Engineer\ndate: 2026-09-01\noutcome: applied\n"
    )
    (vacancy_dir / "sources" / "posting.md").write_text(posting)

    store = ChromaStore(str(tmp_path / "chroma"))
    ingest.ingest_vacancies(tmp_path / "vacancies", store=store, embedder=embedder)
    retriever = Retriever(store=store, embedder=embedder)

    matches = retriever.query_similar_vacancies(query)
    assert len(matches) == 1
    assert MIN_SIMILARITY <= matches[0].similarity < DUPLICATE_SIMILARITY
    assert matches[0].is_duplicate is False


# --- User Story 3: cold start / no match -------------------------------------------------


def test_empty_collection_returns_empty_list(tmp_path, embedder):
    store = ChromaStore(str(tmp_path / "chroma"))
    retriever = Retriever(store=store, embedder=embedder)
    assert retriever.query_similar_vacancies("any job description text") == []


def test_unrelated_jd_returns_empty_list(retriever):
    assert retriever.query_similar_vacancies(UNRELATED_JD) == []


def test_all_matches_are_at_or_above_min_similarity(retriever):
    matches = retriever.query_similar_vacancies(ACME_POSTING)
    assert all(m.similarity >= MIN_SIMILARITY for m in matches)


def test_multiple_chunks_per_vacancy_collapse_to_one_match(tmp_path, embedder):
    # a vacancy folder with two files under sources/ must still yield one match, not two
    vacancy_dir = tmp_path / "vacancies" / "2026-08-01_wonka_confectioner"
    (vacancy_dir / "sources").mkdir(parents=True)
    (vacancy_dir / "vacancy.yaml").write_text(
        "company: Wonka Industries\nposition: Confectioner\ndate: 2026-08-01\noutcome: applied\n"
    )
    (vacancy_dir / "sources" / "posting.md").write_text("Confectioner role at Wonka Industries.")
    (vacancy_dir / "sources" / "posting-repost.md").write_text(
        "Confectioner role at Wonka Industries, reposted."
    )

    store = ChromaStore(str(tmp_path / "chroma"))
    ingest.ingest_vacancies(tmp_path / "vacancies", store=store, embedder=embedder)
    retriever = Retriever(store=store, embedder=embedder)

    matches = retriever.query_similar_vacancies("Confectioner role at Wonka Industries.")
    matching_ids = [m.vacancy_id for m in matches]
    assert matching_ids.count("2026-08-01_wonka-industries_confectioner") == 1


# --- query_bullets (specs/003-analyze-report-generation) --------------------------------


def test_query_bullets_ranks_by_similarity(tmp_path, embedder):
    store = ChromaStore(str(tmp_path / "chroma"))
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    retriever = Retriever(store=store, embedder=embedder)

    results = retriever.query_bullets("FastAPI backend service with Redis caching", top_k=3)
    assert len(results) == 3
    assert results[0]["id"] == "bullet-0"
    similarities = [r["similarity"] for r in results]
    assert similarities == sorted(similarities, reverse=True)


def test_query_bullets_returns_up_to_top_k_regardless_of_score(tmp_path, embedder):
    # unlike query_similar_vacancies, there is no MIN_SIMILARITY cutoff here — bullets are
    # internal LLM context, not a user-facing relevance judgment (research.md)
    store = ChromaStore(str(tmp_path / "chroma"))
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    retriever = Retriever(store=store, embedder=embedder)

    results = retriever.query_bullets(
        "Completely unrelated pastry chef restaurant kitchen", top_k=5
    )
    assert len(results) == 5


def test_query_bullets_empty_collection_returns_empty_list(tmp_path, embedder):
    store = ChromaStore(str(tmp_path / "chroma"))
    retriever = Retriever(store=store, embedder=embedder)
    assert retriever.query_bullets("any text") == []
