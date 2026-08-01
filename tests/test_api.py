from pathlib import Path

import pytest
from _fakes import BagOfWordsEmbedder
from fastapi.testclient import TestClient

from vacancy_radar import ingest
from vacancy_radar.api import app, get_retriever
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.retriever import Retriever

client = TestClient(app)

EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "example"
VACANCIES_DIR = EXAMPLE_DIR / "vacancies"
ACME_POSTING = (
    VACANCIES_DIR / "2026-01-15_acme-corp_backend-engineer" / "sources" / "posting.md"
).read_text()


@pytest.fixture(autouse=True)
def isolated_retriever(tmp_path):
    """Every /similar test gets its own tmp-path-backed store, never the real .cache/chroma."""
    embedder = BagOfWordsEmbedder()
    store = ChromaStore(str(tmp_path / "chroma"))
    app.dependency_overrides[get_retriever] = lambda: Retriever(store=store, embedder=embedder)
    yield store, embedder
    app.dependency_overrides.pop(get_retriever, None)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_not_yet_implemented() -> None:
    response = client.post("/analyze", params={"jd_text": "placeholder"})
    assert response.status_code == 501


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
