import re
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
        self.call_count = 0

    def analyze(self, jd_text, experience_bullets, filter_rules) -> CandidateReport:
        self.call_count += 1
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
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))
    app.dependency_overrides[get_retriever] = lambda: Retriever(store=store, embedder=embedder)
    yield store, embedder
    app.dependency_overrides.pop(get_retriever, None)


@pytest.fixture(autouse=True)
def isolated_llm_provider():
    fake = FakeLLMProvider(_empty_candidate)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


def test_index_page_renders_the_form(isolated_retriever) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'name="jd_text"' in response.text


def test_ui_analyze_renders_full_report(isolated_retriever, isolated_llm_provider) -> None:
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
                )
            ],
            gaps=["No Kubernetes experience found in ingested bullets"],
            draft_sentences=[],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post("/ui/analyze", data={"jd_text": ACME_POSTING})
    assert response.status_code == 200
    assert "Backend" in response.text
    assert "Relevant backend work." in response.text
    assert "No Kubernetes experience found in ingested bullets" in response.text
    assert "Acme Corp" in response.text


# --- User Story 2: trust and reuse the draft paragraph -----------------------------------


def _draft_sentence_factory(jd_text, bullets, filter_rules):
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


def test_ui_analyze_pairs_each_draft_sentence_with_its_citation(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    isolated_llm_provider.candidate_factory = _draft_sentence_factory

    response = client.post("/ui/analyze", data={"jd_text": ACME_POSTING})

    first_bullet_text = Retriever(store=store, embedder=embedder).query_bullets(
        ACME_POSTING, top_k=1
    )[0]["text"]
    blocks = re.findall(
        r'<li class="draft-sentence">.*?</li>', response.text, flags=re.DOTALL
    )
    assert any(
        "I have hands-on backend experience." in block and first_bullet_text in block
        for block in blocks
    )


def test_ui_analyze_copy_target_matches_draft_paragraph_exactly(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    isolated_llm_provider.candidate_factory = _draft_sentence_factory

    response = client.post("/ui/analyze", data={"jd_text": ACME_POSTING})

    match = re.search(
        r'id="draft-paragraph-text"[^>]*>(.*?)</',
        response.text,
        flags=re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == "I have hands-on backend experience."


# --- User Story 3: understand failures without reading logs -------------------------------


def test_ui_analyze_rejects_empty_input_without_calling_the_llm(
    isolated_retriever, isolated_llm_provider
) -> None:
    response = client.post("/ui/analyze", data={"jd_text": "   "})
    assert response.status_code == 200
    assert "job posting" in response.text.lower()
    assert isolated_llm_provider.call_count == 0


def test_ui_analyze_backend_failure_shows_plain_language_message(isolated_retriever) -> None:
    def raising_factory(jd_text, bullets, filter_rules):
        raise LLMProviderError("backend unreachable: connection refused")

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(raising_factory)

    response = client.post("/ui/analyze", data={"jd_text": "Some job posting text."})
    assert response.status_code == 200
    assert "connection refused" not in response.text
    assert "unavailable" in response.text.lower()


def test_ui_analyze_empty_index_shows_nothing_to_show_yet(
    isolated_retriever, isolated_llm_provider
) -> None:
    response = client.post("/ui/analyze", data={"jd_text": "Any job posting text."})
    assert response.status_code == 200
    assert "nothing to show" in response.text.lower()
