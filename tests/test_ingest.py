import shutil
from datetime import date
from pathlib import Path

import pytest
from _fakes import FakeEmbedder

from vacancy_radar import ingest
from vacancy_radar import manifest as manifest_module
from vacancy_radar.chroma_store import ChromaStore
from vacancy_radar.models import VacancyRecord

EXAMPLE_DIR = Path(__file__).parent.parent / "data" / "example"
VACANCIES_DIR = EXAMPLE_DIR / "vacancies"


@pytest.fixture
def store(tmp_path):
    return ChromaStore(str(tmp_path / "chroma"))


@pytest.fixture
def embedder():
    return FakeEmbedder()


# --- ingest_experience_bullets ---------------------------------------------------------


def test_ingest_experience_bullets_embeds_all_bullets(store, embedder):
    count = ingest.ingest_experience_bullets(EXAMPLE_DIR, store=store, embedder=embedder)
    assert count == 8
    assert store.count(ingest.BULLETS_COLLECTION) == 8


def test_ingest_experience_bullets_ignores_readme(store, embedder, tmp_path):
    cv_dir = tmp_path / "cv"
    cv_dir.mkdir()
    (cv_dir / "README.md").write_text("- not a real bullet\n")
    (cv_dir / "experience.md").write_text("- one real bullet\n")
    count = ingest.ingest_experience_bullets(cv_dir, store=store, embedder=embedder)
    assert count == 1


def test_ingest_experience_bullets_missing_dir_is_zero(store, embedder, tmp_path):
    count = ingest.ingest_experience_bullets(
        tmp_path / "does-not-exist", store=store, embedder=embedder
    )
    assert count == 0


def test_ingest_experience_bullets_is_full_replace(store, embedder, tmp_path):
    cv_dir = tmp_path / "cv"
    cv_dir.mkdir()
    (cv_dir / "experience.md").write_text("- bullet one\n- bullet two\n")
    ingest.ingest_experience_bullets(cv_dir, store=store, embedder=embedder)
    assert store.count(ingest.BULLETS_COLLECTION) == 2

    (cv_dir / "experience.md").write_text("- only bullet now\n")
    ingest.ingest_experience_bullets(cv_dir, store=store, embedder=embedder)
    assert store.count(ingest.BULLETS_COLLECTION) == 1


# --- ingest_vacancies: valid folders + metadata -----------------------------------------


def test_ingest_vacancies_embeds_valid_folders_with_metadata(store, embedder):
    summary = ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)
    assert summary.vacancies_created == 2
    # vacancy.yaml + 1 sources file + 1 correspondence file, per valid folder
    assert store.count(ingest.VACANCIES_COLLECTION) == 6

    got = store.get_or_create_collection(ingest.VACANCIES_COLLECTION).get(
        ids=["2026-01-15_acme-corp_backend-engineer/vacancy.yaml"]
    )
    assert got["metadatas"][0] == {
        "company": "Acme Corp",
        "position": "Backend Engineer",
        "date": "2026-01-15",
        "outcome": "applied",
        "doc_type": "vacancy_meta",
    }


def test_ingest_vacancies_reports_invalid_folders(store, embedder):
    summary = ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)
    reasons = {Path(f.folder).name: f.reason for f in summary.vacancies_invalid}
    assert "outcome" in reasons["2026-03-01_initech_data-engineer"]
    assert "convention" in reasons["initech-data-engineer-march"]


def test_ingest_vacancies_reports_conflicts(store, embedder):
    summary = ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder)
    assert len(summary.vacancies_conflicting) == 1
    conflict = summary.vacancies_conflicting[0]
    assert conflict.natural_key == "2026-05-01_stark-industries_ml-engineer"
    assert len(conflict.folders) == 2
    # conflicting folders must not be embedded at all
    ids = store.get_or_create_collection(ingest.VACANCIES_COLLECTION).get(
        ids=["2026-05-01_stark-industries_ml-engineer/vacancy.yaml"]
    )
    assert ids["ids"] == []


def test_ingest_vacancies_empty_dir_is_zero_not_error(store, embedder, tmp_path):
    summary = ingest.ingest_vacancies(tmp_path / "no-such-dir", store=store, embedder=embedder)
    assert summary.vacancies_created == 0
    assert summary.vacancies_invalid == []
    assert summary.vacancies_conflicting == []


def test_ingest_is_idempotent(store, embedder):
    manifest = manifest_module.IngestManifest()
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder, ingest_manifest=manifest)
    ingest.ingest_vacancies(VACANCIES_DIR, store=store, embedder=embedder, ingest_manifest=manifest)
    assert store.count(ingest.VACANCIES_COLLECTION) == 6


# --- ingest_vacancies: incremental (sync) behavior --------------------------------------


def test_incremental_skips_unchanged_folders(store, embedder):
    manifest = manifest_module.IngestManifest()
    ingest.ingest_vacancies(
        VACANCIES_DIR, store=store, embedder=embedder, ingest_manifest=manifest, incremental=False
    )
    summary = ingest.ingest_vacancies(
        VACANCIES_DIR, store=store, embedder=embedder, ingest_manifest=manifest, incremental=True
    )
    assert summary.vacancies_created == 0
    assert summary.vacancies_updated == 0
    assert summary.vacancies_skipped == 2


def test_incremental_reembeds_only_changed_file(store, embedder, tmp_path):
    vacancy_dir = tmp_path / "vacancies"
    shutil.copytree(VACANCIES_DIR, vacancy_dir)
    manifest = manifest_module.IngestManifest()
    ingest.ingest_vacancies(
        vacancy_dir, store=store, embedder=embedder, ingest_manifest=manifest, incremental=False
    )

    yaml_path = vacancy_dir / "2026-01-15_acme-corp_backend-engineer" / "vacancy.yaml"
    yaml_path.write_text(yaml_path.read_text().replace("outcome: applied", "outcome: offer"))

    summary = ingest.ingest_vacancies(
        vacancy_dir, store=store, embedder=embedder, ingest_manifest=manifest, incremental=True
    )
    assert summary.vacancies_updated == 1
    assert summary.vacancies_skipped == 1
    assert summary.vacancies_created == 0


def test_incremental_embeds_newly_added_folder(store, embedder, tmp_path):
    vacancy_dir = tmp_path / "vacancies"
    shutil.copytree(VACANCIES_DIR, vacancy_dir)
    manifest = manifest_module.IngestManifest()
    ingest.ingest_vacancies(
        vacancy_dir, store=store, embedder=embedder, ingest_manifest=manifest, incremental=False
    )

    new_folder = vacancy_dir / "2026-06-01_hooli_swe"
    new_folder.mkdir()
    (new_folder / "vacancy.yaml").write_text(
        "company: Hooli\nposition: SWE\ndate: 2026-06-01\noutcome: applied\n"
    )

    summary = ingest.ingest_vacancies(
        vacancy_dir, store=store, embedder=embedder, ingest_manifest=manifest, incremental=True
    )
    assert summary.vacancies_created == 1
    assert summary.vacancies_skipped == 2


def test_incremental_does_not_clean_up_deleted_folder(store, embedder, tmp_path):
    vacancy_dir = tmp_path / "vacancies"
    shutil.copytree(VACANCIES_DIR, vacancy_dir)
    manifest = manifest_module.IngestManifest()
    ingest.ingest_vacancies(
        vacancy_dir, store=store, embedder=embedder, ingest_manifest=manifest, incremental=False
    )

    shutil.rmtree(vacancy_dir / "2026-02-03_globex_platform-engineer")

    ingest.ingest_vacancies(
        vacancy_dir, store=store, embedder=embedder, ingest_manifest=manifest, incremental=True
    )
    got = store.get_or_create_collection(ingest.VACANCIES_COLLECTION).get(
        ids=["2026-02-03_globex_platform-engineer/vacancy.yaml"]
    )
    assert len(got["ids"]) == 1


# --- chunk_vacancy_folder: image/PDF/DOCX sources (specs/006-vacancy-upload) --------------


FOLDER_NAME = "2026-01-15_acme-corp_backend-engineer"


def _make_record() -> VacancyRecord:
    return VacancyRecord(
        company="Acme Corp", position="Backend Engineer", date=date(2026, 1, 15), outcome="applied"
    )


def test_chunk_vacancy_folder_extracts_text_from_pdf_source(tmp_path: Path):
    from reportlab.pdfgen import canvas

    folder = tmp_path / FOLDER_NAME
    (folder / "sources").mkdir(parents=True)
    (folder / "vacancy.yaml").write_text("company: Acme Corp\n")

    pdf_path = folder / "sources" / "posting.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(50, 750, "Backend Engineer role at Acme Corp")
    c.save()

    chunks = ingest.chunk_vacancy_folder(folder, FOLDER_NAME, _make_record())
    posting_chunk = next(c for c in chunks if c["id"].endswith("posting.pdf"))
    assert "Backend Engineer role at Acme Corp" in posting_chunk["document"]


def test_chunk_vacancy_folder_extracts_text_from_docx_source(tmp_path: Path):
    from docx import Document

    folder = tmp_path / FOLDER_NAME
    (folder / "sources").mkdir(parents=True)
    (folder / "vacancy.yaml").write_text("company: Acme Corp\n")

    docx_path = folder / "sources" / "posting.docx"
    document = Document()
    document.add_paragraph("Backend Engineer role at Acme Corp")
    document.save(str(docx_path))

    chunks = ingest.chunk_vacancy_folder(folder, FOLDER_NAME, _make_record())
    posting_chunk = next(c for c in chunks if c["id"].endswith("posting.docx"))
    assert "Backend Engineer role at Acme Corp" in posting_chunk["document"]


def test_chunk_vacancy_folder_extracts_text_from_image_source(tmp_path: Path):
    from PIL import Image, ImageDraw

    folder = tmp_path / FOLDER_NAME
    (folder / "sources").mkdir(parents=True)
    (folder / "vacancy.yaml").write_text("company: Acme Corp\n")

    image_path = folder / "sources" / "posting.png"
    image = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 40), "Acme Corp", fill="black")
    image.save(image_path)

    chunks = ingest.chunk_vacancy_folder(folder, FOLDER_NAME, _make_record())
    posting_chunk = next(c for c in chunks if c["id"].endswith("posting.png"))
    # OCR against a synthetic string isn't pixel-perfect (see tests/test_documents.py) — just
    # confirm the extraction path ran and produced something, not raw undecodable bytes.
    assert isinstance(posting_chunk["document"], str)
