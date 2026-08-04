import io
import re

import pytest
import yaml
from _fakes import BagOfWordsEmbedder
from fastapi.testclient import TestClient

from vacancy_radar.api import app, get_chroma_store, get_embedder, get_llm_provider, get_vacancy_dir
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.llm.base import LLMProvider
from vacancy_radar.models import CandidateReport, DraftVacancyMetadata

client = TestClient(app)


class FakeDraftLLMProvider(LLMProvider):
    def __init__(self, draft_factory=None, error: Exception | None = None) -> None:
        self.draft_factory = draft_factory
        self.error = error
        self.call_count = 0
        self.last_image_bytes: bytes | None = None
        self.last_image_media_type: str | None = None

    def analyze(self, jd_text, experience_bullets, filter_rules) -> CandidateReport:
        raise NotImplementedError("not exercised by this test file's fakes")

    def draft_vacancy_metadata(
        self,
        document_text: str,
        image_bytes: bytes | None = None,
        image_media_type: str | None = None,
    ) -> DraftVacancyMetadata:
        self.call_count += 1
        self.last_image_bytes = image_bytes
        self.last_image_media_type = image_media_type
        if self.error:
            raise self.error
        return self.draft_factory(document_text)

    def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str:
        raise NotImplementedError("not exercised by this test file's fakes")


def _default_draft(document_text: str) -> DraftVacancyMetadata:
    return DraftVacancyMetadata(company="Acme Corp", position="Backend Engineer", date="2026-01-15")


@pytest.fixture(autouse=True)
def isolated_llm_provider():
    fake = FakeDraftLLMProvider(draft_factory=_default_draft)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_llm_provider, None)


@pytest.fixture(autouse=True)
def isolated_vacancy_dir(tmp_path):
    vacancy_dir = tmp_path / "vacancies"
    vacancy_dir.mkdir()
    app.dependency_overrides[get_vacancy_dir] = lambda: vacancy_dir
    yield vacancy_dir
    app.dependency_overrides.pop(get_vacancy_dir, None)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    """The confirm route writes to this same store/embedder that /similar reads from
    (specs/006-vacancy-upload) — overriding both keeps every route consistent."""
    store = ChromaStore(str(tmp_path / "chroma"))
    embedder = BagOfWordsEmbedder()
    app.dependency_overrides[get_chroma_store] = lambda: store
    app.dependency_overrides[get_embedder] = lambda: embedder
    yield store, embedder
    app.dependency_overrides.pop(get_chroma_store, None)
    app.dependency_overrides.pop(get_embedder, None)


def test_ingest_page_renders_upload_form(isolated_vacancy_dir) -> None:
    response = client.get("/ingest")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "multipart/form-data" in response.text


def test_ingest_page_has_nav_link_back_to_analyze(isolated_vacancy_dir) -> None:
    response = client.get("/ingest")
    assert '<nav class="site-nav">' in response.text
    assert '<a href="/"' in response.text


def test_ingest_page_shows_upload_step(isolated_vacancy_dir) -> None:
    response = client.get("/ingest")
    assert 'data-step="upload"' in response.text


def test_ingest_draft_renders_prefilled_fields(
    isolated_vacancy_dir, isolated_llm_provider
) -> None:
    response = client.post(
        "/ingest/draft",
        files={
            "file": (
                "posting.txt",
                io.BytesIO(b"Acme Corp is hiring a Backend Engineer"),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    assert "Acme Corp" in response.text
    assert "Backend Engineer" in response.text
    assert "upload_token" in response.text


def test_ingest_draft_success_shows_review_step(
    isolated_vacancy_dir, isolated_llm_provider
) -> None:
    response = client.post(
        "/ingest/draft",
        files={"file": ("posting.txt", io.BytesIO(b"Acme Corp posting"), "text/plain")},
    )
    assert 'data-step="review"' in response.text


def test_ingest_draft_failure_shows_error_step(isolated_vacancy_dir) -> None:
    from vacancy_radar.llm.base import LLMProviderError

    app.dependency_overrides[get_llm_provider] = lambda: FakeDraftLLMProvider(
        error=LLMProviderError("backend unreachable")
    )

    response = client.post(
        "/ingest/draft",
        files={"file": ("posting.txt", io.BytesIO(b"Acme Corp posting"), "text/plain")},
    )
    assert 'data-step="error"' in response.text
    assert 'class="error"' in response.text


def _draft_upload(filename: str = "posting.txt", content: bytes = b"Acme Corp posting") -> str:
    """POST /ui/ingest/draft and return the upload_token from the rendered review form."""
    response = client.post(
        "/ingest/draft",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    match = re.search(r'name="upload_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


# --- User Story 2: review and correct the draft before it's saved ------------------------


def test_confirm_writes_edited_values_not_the_original_draft(isolated_vacancy_dir) -> None:
    token = _draft_upload()

    response = client.post(
        "/ingest/confirm",
        data={
            "upload_token": token,
            "original_filename": "posting.txt",
            "company": "Edited Corp",  # deliberately different from the drafted "Acme Corp"
            "position": "Backend Engineer",
            "date": "2026-01-15",
            "outcome": "applied",
        },
    )
    assert response.status_code == 200

    folder = isolated_vacancy_dir / "2026-01-15_edited-corp_backend-engineer"
    assert folder.is_dir()
    record = yaml.safe_load((folder / "vacancy.yaml").read_text())
    assert record["company"] == "Edited Corp"
    assert record["outcome"] == "applied"
    assert (folder / "sources" / "posting.txt").exists()
    assert 'data-step="done"' in response.text


def test_confirm_rejects_missing_outcome(isolated_vacancy_dir) -> None:
    token = _draft_upload()

    response = client.post(
        "/ingest/confirm",
        data={
            "upload_token": token,
            "original_filename": "posting.txt",
            "company": "Acme Corp",
            "position": "Backend Engineer",
            "date": "2026-01-15",
            "outcome": "",
        },
    )
    assert response.status_code == 200
    assert list(isolated_vacancy_dir.iterdir()) == []
    assert 'data-step="error"' in response.text
    assert 'class="error"' in response.text


def test_never_confirming_creates_no_vacancy_folder(isolated_vacancy_dir) -> None:
    _draft_upload()
    assert list(isolated_vacancy_dir.iterdir()) == []


# --- User Story 3: immediately retrievable, conflicts surfaced ---------------------------

POSTING_TEXT = "Backend Engineer role building Python APIs with FastAPI and PostgreSQL."


def _confirm(token: str, **overrides):
    data = {
        "upload_token": token,
        "original_filename": "posting.txt",
        "company": "Acme Corp",
        "position": "Backend Engineer",
        "date": "2026-01-15",
        "outcome": "applied",
    }
    data.update(overrides)
    return client.post("/ingest/confirm", data=data)


def test_confirmed_vacancy_is_immediately_searchable_via_similar(isolated_vacancy_dir) -> None:
    token = _draft_upload(filename="posting.txt", content=POSTING_TEXT.encode())
    confirm_response = _confirm(token)
    assert confirm_response.status_code == 200
    assert "searchable" in confirm_response.text.lower()

    response = client.post("/api/similar", params={"jd_text": POSTING_TEXT})
    assert response.status_code == 200
    body = response.json()
    assert any(v["vacancy_id"] == "2026-01-15_acme-corp_backend-engineer" for v in body)


# --- Vision-based drafting for image uploads (specs/007-vision-drafting) -----------------


def test_draft_image_upload_never_calls_extract_text_and_passes_image_bytes(
    isolated_llm_provider, monkeypatch
) -> None:
    from vacancy_radar import documents

    calls = []
    monkeypatch.setattr(
        documents, "extract_text", lambda path: calls.append(path) or "SHOULD_NOT_BE_CALLED"
    )

    response = client.post(
        "/ingest/draft",
        files={"file": ("posting.png", io.BytesIO(b"fake-png-bytes"), "image/png")},
    )

    assert response.status_code == 200
    assert calls == []  # documents.extract_text() is never called for images
    assert isolated_llm_provider.call_count == 1
    assert isolated_llm_provider.last_image_bytes == b"fake-png-bytes"
    assert isolated_llm_provider.last_image_media_type == "image/png"
    assert "Acme Corp" in response.text  # the fake draft still renders


def test_draft_image_upload_shows_specific_message_when_vision_fails(
    isolated_vacancy_dir,
) -> None:
    from vacancy_radar.llm.base import LLMProviderError

    app.dependency_overrides[get_llm_provider] = lambda: FakeDraftLLMProvider(
        error=LLMProviderError("model does not support images")
    )

    response = client.post(
        "/ingest/draft",
        files={"file": ("posting.png", io.BytesIO(b"fake-png-bytes"), "image/png")},
    )

    assert response.status_code == 200
    lower_text = response.text.lower()
    assert "read this image" in lower_text or "can't read images" in lower_text
    assert "model does not support images" not in response.text  # no raw exception text leaks


def test_draft_non_image_upload_shows_generic_message_when_llm_fails(
    isolated_vacancy_dir,
) -> None:
    from vacancy_radar.llm.base import LLMProviderError

    app.dependency_overrides[get_llm_provider] = lambda: FakeDraftLLMProvider(
        error=LLMProviderError("backend unreachable")
    )

    response = client.post(
        "/ingest/draft",
        files={"file": ("posting.txt", io.BytesIO(b"Acme Corp posting"), "text/plain")},
    )

    assert response.status_code == 200
    # the image-specific wording must not appear for a non-image failure
    assert "read this image" not in response.text.lower()
    assert "fill in every field manually" in response.text.lower()


def test_confirm_surfaces_cross_folder_conflict_without_overwriting(isolated_vacancy_dir) -> None:
    # A pre-existing, differently-named folder whose vacancy.yaml resolves to the SAME
    # natural key as the upload below — the pre-write same-path guard (research.md #5) can't
    # catch this, since the folder names differ; ingest_vacancies()'s own cross-folder conflict
    # detection (reused unchanged) is the safety net for this case.
    existing_folder = isolated_vacancy_dir / "2026-01-15_acme-corp_backend-engineer-old"
    (existing_folder / "sources").mkdir(parents=True)
    existing_folder.joinpath("vacancy.yaml").write_text(
        "company: Acme Corp\nposition: Backend Engineer\ndate: 2026-01-15\noutcome: rejected\n"
    )
    existing_folder.joinpath("sources", "posting.md").write_text(POSTING_TEXT)

    token = _draft_upload(filename="posting.txt", content=POSTING_TEXT.encode())
    response = _confirm(token)

    assert response.status_code == 200
    assert "conflict" in response.text.lower()
    # the pre-existing folder's own vacancy.yaml is completely untouched
    assert existing_folder.joinpath("vacancy.yaml").read_text() == (
        "company: Acme Corp\nposition: Backend Engineer\ndate: 2026-01-15\noutcome: rejected\n"
    )
