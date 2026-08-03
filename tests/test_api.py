from pathlib import Path

import pytest
from _fakes import BagOfWordsEmbedder
from fastapi.testclient import TestClient

from vacancy_radar import ingest
from vacancy_radar.api import app, get_llm_provider, get_retriever
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.llm.base import LLMProvider, LLMProviderError
from vacancy_radar.models import (
    CandidateFlag,
    CandidateReport,
    CandidateSentence,
    DraftVacancyMetadata,
)
from vacancy_radar.retriever import Retriever

client = TestClient(app)

EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "example"
VACANCIES_DIR = EXAMPLE_DIR / "vacancies"
ACME_POSTING = (
    VACANCIES_DIR / "2026-01-15_acme-corp_backend-engineer" / "sources" / "posting.md"
).read_text()


class FakeLLMProvider(LLMProvider):
    def __init__(self, candidate_factory) -> None:
        self.candidate_factory = candidate_factory

    def analyze(self, jd_text, experience_bullets, filter_rules) -> CandidateReport:
        return self.candidate_factory(jd_text, experience_bullets, filter_rules)

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        raise NotImplementedError("not exercised by this test file's fakes")


def _empty_candidate(jd_text, bullets, filter_rules) -> CandidateReport:
    return CandidateReport(match_band="poor", flags=[], gaps=[], draft_sentences=[])


@pytest.fixture(autouse=True)
def isolated_retriever(tmp_path):
    """Every test gets its own tmp-path-backed store, never the real .cache/chroma."""
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))
    app.dependency_overrides[get_retriever] = lambda: Retriever(store=store, embedder=embedder)
    yield store, embedder
    app.dependency_overrides.pop(get_retriever, None)


@pytest.fixture(autouse=True)
def isolated_llm_provider():
    """Every /analyze test gets a fake LLM — no real network calls in the automated suite."""
    fake = FakeLLMProvider(_empty_candidate)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_similar_returns_ranked_matches(isolated_retriever) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)

    response = client.post("/similar", params={"jd_text": ACME_POSTING})
    assert response.status_code == 200
    body = response.json()
    assert body[0]["vacancy_id"] == "2026-01-15_acme-corp_backend-engineer"
    assert body[0]["company"] == "Acme Corp"
    assert body[0]["position"] == "Backend Engineer"
    assert body[0]["outcome"] == "applied"
    assert "excerpt" in body[0]


def test_similar_flags_duplicate_application(isolated_retriever) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)

    response = client.post("/similar", params={"jd_text": ACME_POSTING})
    assert response.json()[0]["is_duplicate"] is True


def test_similar_empty_index_returns_empty_list(isolated_retriever) -> None:
    response = client.post("/similar", params={"jd_text": "any job description text"})
    assert response.status_code == 200
    assert response.json() == []


def test_similar_rejects_empty_jd_text(isolated_retriever) -> None:
    response = client.post("/similar", params={"jd_text": "   "})
    assert response.status_code == 422


# --- /analyze (specs/003-analyze-report-generation) --------------------------------------


def test_analyze_returns_grounded_flags_and_gaps(isolated_retriever, isolated_llm_provider) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)

    def factory(jd_text, bullets, filter_rules):
        bullet_id, bullet_text = bullets[0]
        return CandidateReport(
            match_band="good",
            flags=[
                CandidateFlag(
                    label="Backend",
                    severity="green",
                    reason="Relevant backend work.",
                    quote=bullet_text,
                    source_id=bullet_id,
                ),
                CandidateFlag(
                    label="Fabricated",
                    severity="green",
                    reason="Invented.",
                    quote="a claim that appears nowhere in the source",
                    source_id=bullet_id,
                ),
            ],
            gaps=["No Kubernetes experience found in ingested bullets"],
            draft_sentences=[],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post("/analyze", params={"jd_text": ACME_POSTING})
    assert response.status_code == 200
    body = response.json()
    assert body["score"] == "good"
    assert len(body["flags"]) == 1
    assert body["flags"][0]["label"] == "Backend"
    assert body["gaps"] == ["No Kubernetes experience found in ingested bullets"]


def test_analyze_draft_paragraph_contains_only_grounded_claims(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)

    def factory(jd_text, bullets, filter_rules):
        bullet_id, bullet_text = bullets[0]
        return CandidateReport(
            match_band="good",
            flags=[],
            gaps=[],
            draft_sentences=[
                CandidateSentence(
                    text="I have hands-on backend experience.",
                    quote=bullet_text,
                    source_id=bullet_id,
                ),
                CandidateSentence(
                    text="I also invented cold fusion.",
                    quote="invented cold fusion",
                    source_id=bullet_id,
                ),
            ],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post("/analyze", params={"jd_text": ACME_POSTING})
    body = response.json()
    assert body["draft_paragraph"] == "I have hands-on backend experience."
    assert len(body["citations"]) == 1


def test_analyze_empty_index_returns_empty_report_not_error(
    isolated_retriever, isolated_llm_provider
) -> None:
    # Even a provider that tries to claim things without any real bullets to ground them in
    # (e.g. citing a bullet-0 that was never ingested) must have those claims stripped — but
    # gaps (which need no citation, per spec Assumptions) still pass through untouched.
    def factory(jd_text, bullets, filter_rules):
        return CandidateReport(
            match_band="poor",
            flags=[
                CandidateFlag(
                    label="Backend",
                    severity="green",
                    reason="Claims relevant experience.",
                    quote="some experience",
                    source_id="bullet-0",
                )
            ],
            gaps=["No experience data available to assess this posting"],
            draft_sentences=[],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post("/analyze", params={"jd_text": "any job description text"})
    assert response.status_code == 200
    body = response.json()
    assert body["flags"] == []
    assert body["draft_paragraph"] == ""
    assert body["citations"] == []
    assert body["gaps"] == ["No experience data available to assess this posting"]


def test_analyze_rejects_empty_jd_text(isolated_retriever, isolated_llm_provider) -> None:
    response = client.post("/analyze", params={"jd_text": "   "})
    assert response.status_code == 422


def test_analyze_returns_502_on_llm_provider_error(isolated_retriever) -> None:
    def raising_factory(jd_text, bullets, filter_rules):
        raise LLMProviderError("backend unreachable")

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(raising_factory)

    response = client.post("/analyze", params={"jd_text": "some JD text"})
    assert response.status_code == 502


def test_analyze_draft_sentences_matches_draft_paragraph(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)

    def factory(jd_text, bullets, filter_rules):
        bullet_id, bullet_text = bullets[0]
        return CandidateReport(
            match_band="good",
            flags=[],
            gaps=[],
            draft_sentences=[
                CandidateSentence(
                    text="I have hands-on backend experience.",
                    quote=bullet_text,
                    source_id=bullet_id,
                )
            ],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post("/analyze", params={"jd_text": ACME_POSTING})
    body = response.json()
    assert body["draft_sentences"] == [
        {
            "text": "I have hands-on backend experience.",
            "citation": body["citations"][0],
        }
    ]
    assert body["draft_paragraph"] == " ".join(d["text"] for d in body["draft_sentences"])


def test_analyze_similar_field_matches_direct_similar_call(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)

    similar_response = client.post("/similar", params={"jd_text": ACME_POSTING})
    analyze_response = client.post("/analyze", params={"jd_text": ACME_POSTING})

    assert analyze_response.status_code == 200
    assert analyze_response.json()["similar"] == similar_response.json()
