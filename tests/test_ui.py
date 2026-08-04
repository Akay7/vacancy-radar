import re
from pathlib import Path

import pytest
from _fakes import BagOfWordsEmbedder
from fastapi.testclient import TestClient

from vacancy_radar import ingest
from vacancy_radar.api import app, get_llm_provider, get_retriever, get_vacancy_dir
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
    def __init__(
        self,
        candidate_factory,
        draft_factory=None,
        draft_error: Exception | None = None,
        extract_text_factory=None,
        extract_text_error: Exception | None = None,
    ) -> None:
        self.candidate_factory = candidate_factory
        self.draft_factory = draft_factory
        self.draft_error = draft_error
        self.extract_text_factory = extract_text_factory
        self.extract_text_error = extract_text_error
        self.call_count = 0
        self.extract_document_text_calls: list[tuple[bytes, str]] = []

    def analyze(self, jd_text, experience_bullets, filter_rules) -> CandidateReport:
        self.call_count += 1
        return self.candidate_factory(jd_text, experience_bullets, filter_rules)

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        if self.draft_error:
            raise self.draft_error
        if self.draft_factory is None:
            raise NotImplementedError("not exercised by this test file's fakes")
        return self.draft_factory(document_text)

    def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str:
        self.extract_document_text_calls.append((image_bytes, image_media_type))
        if self.extract_text_error:
            raise self.extract_text_error
        if self.extract_text_factory is None:
            raise NotImplementedError("not exercised by this test file's fakes")
        return self.extract_text_factory()


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


def test_index_page_has_nav_link_to_ingest() -> None:
    response = client.get("/")
    assert '<nav class="site-nav">' in response.text
    assert '<a href="/ingest"' in response.text


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

    response = client.post("/analyze", data={"jd_text": ACME_POSTING})
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

    response = client.post("/analyze", data={"jd_text": ACME_POSTING})

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

    response = client.post("/analyze", data={"jd_text": ACME_POSTING})

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
    response = client.post("/analyze", data={"jd_text": "   "})
    assert response.status_code == 200
    assert "job posting" in response.text.lower()
    assert isolated_llm_provider.call_count == 0


def test_ui_analyze_backend_failure_shows_plain_language_message(isolated_retriever) -> None:
    def raising_factory(jd_text, bullets, filter_rules):
        raise LLMProviderError("backend unreachable: connection refused")

    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(raising_factory)

    response = client.post("/analyze", data={"jd_text": "Some job posting text."})
    assert response.status_code == 200
    assert "connection refused" not in response.text
    assert 'class="error"' in response.text
    assert "unavailable" in response.text.lower()


def test_ui_analyze_empty_index_shows_nothing_to_show_yet(
    isolated_retriever, isolated_llm_provider
) -> None:
    response = client.post("/analyze", data={"jd_text": "Any job posting text."})
    assert response.status_code == 200
    assert "nothing to show" in response.text.lower()


# --- User Story 3: shared visual style across pages (specs/008-ingest-flow-clarity) -------


def test_shared_stylesheet_defines_nav_and_error_styles() -> None:
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert ".site-nav" in response.text
    assert ".error" in response.text


# --- specs/009-analyze-and-log-vacancy: analyze an uploaded document ----------------------


def test_ui_analyze_with_uploaded_text_file_produces_a_report(
    isolated_retriever, isolated_llm_provider, monkeypatch
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)

    extract_text_calls = []
    monkeypatch.setattr(
        "vacancy_radar.api.documents.extract_text",
        lambda path: extract_text_calls.append(path) or ACME_POSTING,
    )
    isolated_llm_provider.draft_factory = lambda document_text: DraftVacancyMetadata(
        company="Acme Corp", position="Backend Engineer", date="2026-01-15"
    )

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
            gaps=[],
            draft_sentences=[],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post(
        "/analyze",
        files={"file": ("posting.txt", ACME_POSTING.encode(), "text/plain")},
    )

    assert response.status_code == 200
    assert "Backend" in response.text
    assert "Relevant backend work." in response.text
    assert len(extract_text_calls) == 1  # documents.extract_text used, not extract_document_text
    assert isolated_llm_provider.extract_document_text_calls == []


def test_ui_analyze_with_uploaded_image_uses_vision_extraction_not_local_extraction(
    isolated_retriever, isolated_llm_provider, monkeypatch
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)

    extract_text_calls = []
    monkeypatch.setattr(
        "vacancy_radar.api.documents.extract_text",
        lambda path: extract_text_calls.append(path) or "SHOULD_NOT_BE_CALLED",
    )
    isolated_llm_provider.extract_text_factory = lambda: ACME_POSTING
    isolated_llm_provider.draft_factory = lambda document_text: DraftVacancyMetadata(
        company="Acme Corp", position="Backend Engineer", date="2026-01-15"
    )

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
            gaps=[],
            draft_sentences=[],
        )

    isolated_llm_provider.candidate_factory = factory

    response = client.post(
        "/analyze",
        files={"file": ("posting.png", b"fake-png-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert "Backend" in response.text
    assert extract_text_calls == []  # documents.extract_text never called for images
    assert len(isolated_llm_provider.extract_document_text_calls) == 1
    assert isolated_llm_provider.extract_document_text_calls[0] == (b"fake-png-bytes", "image/png")


# --- specs/009-analyze-and-log-vacancy: log the vacancy right where it was analyzed -------


@pytest.fixture
def isolated_vacancy_dir(tmp_path):
    vacancy_dir = tmp_path / "vacancies"
    vacancy_dir.mkdir()
    app.dependency_overrides[get_vacancy_dir] = lambda: vacancy_dir
    yield vacancy_dir
    app.dependency_overrides.pop(get_vacancy_dir, None)


def test_ui_analyze_with_upload_shows_draft_fields_alongside_report(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    isolated_llm_provider.draft_factory = lambda document_text: DraftVacancyMetadata(
        company="Acme Corp", position="Backend Engineer", date="2026-01-15"
    )

    response = client.post(
        "/analyze",
        files={"file": ("posting.txt", ACME_POSTING.encode(), "text/plain")},
    )

    assert response.status_code == 200
    assert "upload_token" in response.text
    assert 'value="Acme Corp"' in response.text
    assert 'value="Backend Engineer"' in response.text
    assert 'hx-post="/ingest/confirm"' in response.text


def test_ui_analyze_upload_token_saves_via_existing_confirm_route(
    isolated_retriever, isolated_llm_provider, isolated_vacancy_dir
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    isolated_llm_provider.draft_factory = lambda document_text: DraftVacancyMetadata(
        company="Acme Corp", position="Backend Engineer", date="2026-01-15"
    )

    draft_response = client.post(
        "/analyze",
        files={"file": ("posting.txt", ACME_POSTING.encode(), "text/plain")},
    )
    token_match = re.search(r'name="upload_token" value="([^"]+)"', draft_response.text)
    assert token_match is not None

    confirm_response = client.post(
        "/ingest/confirm",
        data={
            "upload_token": token_match.group(1),
            "original_filename": "posting.txt",
            "company": "Acme Corp",
            "position": "Backend Engineer",
            "date": "2026-01-15",
            "outcome": "applied",
        },
    )

    assert confirm_response.status_code == 200
    folder = isolated_vacancy_dir / "2026-01-15_acme-corp_backend-engineer"
    assert folder.is_dir()
    assert (folder / "sources" / "posting.txt").exists()


def test_ui_analyze_report_and_draft_fail_independently(
    isolated_retriever, isolated_llm_provider
) -> None:
    store, embedder = isolated_retriever
    ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)

    # Drafting fails, analysis succeeds — the report must still render in full.
    isolated_llm_provider.draft_error = LLMProviderError("drafting backend unavailable")

    def factory(jd_text, bullets, filter_rules):
        return CandidateReport(match_band="good", flags=[], gaps=[], draft_sentences=[])

    isolated_llm_provider.candidate_factory = factory

    response = client.post(
        "/analyze",
        files={"file": ("posting.txt", ACME_POSTING.encode(), "text/plain")},
    )

    assert response.status_code == 200
    assert "Match:" in response.text and "good" in response.text
    assert "fill in every field manually" in response.text.lower()


# --- specs/009-analyze-and-log-vacancy: pasting text still just gives a report ------------


def test_ui_analyze_paste_text_has_no_upload_token_or_draft_block(
    isolated_retriever, isolated_llm_provider
) -> None:
    response = client.post("/analyze", data={"jd_text": "Some job posting text."})

    assert response.status_code == 200
    assert "upload_token" not in response.text
    assert "Log this vacancy" not in response.text
