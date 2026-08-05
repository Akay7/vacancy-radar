import shutil
import sys
from datetime import date
from pathlib import Path

import lancedb
import pytest

from vacancy_radar import frontmatter
from vacancy_radar.index.build import build_index
from vacancy_radar.index.embed import DEFAULT_EMBEDDING_MODEL_NAME
from vacancy_radar.index.schema import read_embedding_model
from vacancy_radar.models import Company, Document, DocumentKind, Status, Vacancy
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import VaultWarning, read_vault

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from generate import generate_vault  # noqa: E402

FIXTURE_VAULT = _FIXTURES_DIR / "vault"


def _init_vault(vault: Path) -> None:
    (vault / VAULT_MARKER_DIRNAME).mkdir(parents=True, exist_ok=True)


def _write_company(vault: Path, slug: str, name: str) -> None:
    company_dir = vault / slug
    company_dir.mkdir(parents=True, exist_ok=True)
    company = Company(slug=slug, name=name, domains=[f"{slug}.example"])
    metadata = company.model_dump(mode="json", exclude_none=True)
    (company_dir / "_company.md").write_text(
        frontmatter.serialize(metadata, ""), encoding="utf-8"
    )


def _write_vacancy(vault: Path, slug: str, dirname: str, vacancy: Vacancy) -> Path:
    vacancy_dir = vault / slug / dirname
    vacancy_dir.mkdir(parents=True, exist_ok=True)
    metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    (vacancy_dir / "vacancy.md").write_text(
        frontmatter.serialize(metadata, f"# {vacancy.role}\n"), encoding="utf-8"
    )
    return vacancy_dir


def _write_document(
    vacancy_dir: Path, document: Document, body: str = "Some document body text."
) -> Path:
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    metadata = document.model_dump(mode="json", exclude_none=True)
    path = docs_dir / f"{document.id}.md"
    path.write_text(frontmatter.serialize(metadata, body), encoding="utf-8")
    return path


def _write_sidecar(
    docs_dir: Path,
    source_name: str,
    *,
    body: str = "Extracted sidecar text.",
    manually_corrected: bool = False,
) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "extracted_from": source_name,
        "source_hash": "sha256:deadbeef",
        "extractor": "pypdf-6.14.2",
        "extracted_at": "2026-01-01",
        "manually_corrected": manually_corrected,
    }
    path = docs_dir / f"{source_name}.md"
    path.write_text(frontmatter.serialize(metadata, body), encoding="utf-8")
    return path


def _simple_vacancy(
    vacancy_id: str, slug: str = "acme", **overrides: object
) -> Vacancy:
    fields: dict[str, object] = {
        "id": vacancy_id,
        "company": "Acme",
        "company_slug": slug,
        "role": "Engineer",
        "source_url": f"https://jobs.{slug}.example/{vacancy_id}",
        "status": Status.FOUND,
        "found_date": date(2026, 1, 1),
    }
    fields.update(overrides)
    return Vacancy(**fields)  # type: ignore[arg-type]


def _small_vault(tmp_path: Path) -> Path:
    """One company, one vacancy, two documents - a minimal fixture for
    fast, focused build tests."""
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc1",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="Note",
            date=date(2026, 1, 2),
        ),
        body="A note about this role that seems promising.",
    )
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc2",
            vacancy_id="v1",
            kind=DocumentKind.EMAIL,
            title="Email",
            date=date(2026, 1, 3),
        ),
        body="Thanks for applying, we would like to schedule a call.",
    )
    return vault


# --- Embedding-model provenance (stage 4) -----------------------------------

_OTHER_DIM_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
"""A second model, cached locally, whose native dimension (512) differs
from `DEFAULT_EMBEDDING_MODEL_NAME`'s (384) - used only to exercise the
dimension-mismatch recreate path, never for embedding quality."""


@pytest.mark.embedding
def test_fresh_build_records_the_model_it_was_called_with(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"

    build_index(read_vault(vault), index_path, model_name=DEFAULT_EMBEDDING_MODEL_NAME)

    table = lancedb.connect(index_path).open_table("documents")
    assert read_embedding_model(table) == DEFAULT_EMBEDDING_MODEL_NAME


@pytest.mark.embedding
def test_dimension_mismatch_recreate_records_the_new_model(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path, model_name=DEFAULT_EMBEDDING_MODEL_NAME)

    build_index(read_vault(vault), index_path, model_name=_OTHER_DIM_MODEL_NAME)

    table = lancedb.connect(index_path).open_table("documents")
    assert read_embedding_model(table) == _OTHER_DIM_MODEL_NAME


@pytest.mark.embedding
def test_incremental_build_with_unchanged_model_leaves_metadata_untouched(
    tmp_path: Path,
) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path, model_name=DEFAULT_EMBEDDING_MODEL_NAME)

    build_index(read_vault(vault), index_path, model_name=DEFAULT_EMBEDDING_MODEL_NAME)

    table = lancedb.connect(index_path).open_table("documents")
    assert read_embedding_model(table) == DEFAULT_EMBEDDING_MODEL_NAME


# --- Section 11: building from empty ---------------------------------------


@pytest.mark.embedding
def test_building_from_empty_over_fixture_vault_produces_expected_row_count(
    tmp_path: Path,
) -> None:
    snapshot = read_vault(FIXTURE_VAULT)
    index_path = tmp_path / ".index"

    build_index(snapshot, index_path)

    table = lancedb.connect(index_path).open_table("documents")
    expected = len(snapshot.documents) + len(snapshot.vacancies)
    assert table.count_rows() == expected


@pytest.mark.embedding
def test_every_row_content_hash_matches_snapshot_hash(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    snapshot = read_vault(vault)
    index_path = tmp_path / ".index"

    build_index(snapshot, index_path)

    table = lancedb.connect(index_path).open_table("documents")
    rows = table.to_arrow().to_pylist()

    for row in rows:
        assert row["content_hash"] == snapshot.hashes[Path(row["path"])]


@pytest.mark.embedding
def test_denormalized_fields_match_parent_vacancy(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    snapshot = read_vault(vault)
    index_path = tmp_path / ".index"

    build_index(snapshot, index_path)

    table = lancedb.connect(index_path).open_table("documents")
    rows = {row["doc_id"]: row for row in table.to_arrow().to_pylist()}

    vacancy = snapshot.vacancies["v1"]
    doc_row = rows["v1-doc1"]
    assert doc_row["company_slug"] == vacancy.company_slug
    assert doc_row["company"] == vacancy.company
    assert doc_row["role"] == vacancy.role
    assert doc_row["status"] == vacancy.status.value


@pytest.mark.embedding
def test_source_with_sidecar_embeds_sidecar_text(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "spec.pdf").write_bytes(b"%PDF fake bytes")
    _write_sidecar(docs_dir, "spec.pdf", body="The extracted take-home spec text.")

    snapshot = read_vault(vault)
    index_path = tmp_path / ".index"
    build_index(snapshot, index_path)

    table = lancedb.connect(index_path).open_table("documents")
    rows = {row["doc_id"]: row for row in table.to_arrow().to_pylist()}

    assert "The extracted take-home spec text." in rows["spec.pdf"]["text"]


@pytest.mark.embedding
def test_source_without_sidecar_indexes_by_filename(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "assignment.pdf").write_bytes(b"%PDF fake bytes, no sidecar")

    snapshot = read_vault(vault)
    index_path = tmp_path / ".index"
    build_index(snapshot, index_path)

    table = lancedb.connect(index_path).open_table("documents")
    rows = {row["doc_id"]: row for row in table.to_arrow().to_pylist()}

    assert rows["assignment.pdf"]["text"].strip() != ""
    assert "assignment.pdf" in rows["assignment.pdf"]["text"]


def _rows_by_id(index_path: Path) -> dict[str, dict]:
    table = lancedb.connect(index_path).open_table("documents")
    return {row["doc_id"]: row for row in table.to_arrow().to_pylist()}


def _fake_warning() -> VaultWarning:
    return VaultWarning(kind="fake_preexisting_warning", message="pre-existing")


# --- Section 12: incrementality ---------------------------------------------


@pytest.mark.embedding
def test_building_twice_with_no_change_embeds_nothing(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)

    report = build_index(read_vault(vault), index_path)

    assert report.added == 0
    assert report.changed == 0
    assert report.deleted == 0


@pytest.mark.embedding
def test_editing_one_document_body_reembeds_exactly_that_document(
    tmp_path: Path,
) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)
    before = _rows_by_id(index_path)

    doc1_path = vault / "acme" / "v1" / "documents" / "v1-doc1.md"
    metadata, _ = frontmatter.parse(doc1_path.read_text(encoding="utf-8"))
    doc1_path.write_text(
        frontmatter.serialize(metadata, "A completely different note body now."),
        encoding="utf-8",
    )

    report = build_index(read_vault(vault), index_path)
    after = _rows_by_id(index_path)

    assert report.changed == 1
    assert after["v1-doc1"]["content_hash"] != before["v1-doc1"]["content_hash"]
    assert after["v1-doc1"]["vector"] != before["v1-doc1"]["vector"]
    assert after["v1-doc2"]["content_hash"] == before["v1-doc2"]["content_hash"]
    assert after["v1-doc2"]["vector"] == before["v1-doc2"]["vector"]


@pytest.mark.embedding
def test_frontmatter_only_vacancy_edit_reembeds_vacancy_row_and_syncs_siblings(
    tmp_path: Path,
) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)
    before = _rows_by_id(index_path)

    vacancy = _simple_vacancy(
        "v1", status=Status.APPLIED, applied_date=date(2026, 1, 5)
    )
    _write_vacancy(vault, "acme", "v1", vacancy)

    build_index(read_vault(vault), index_path)
    after = _rows_by_id(index_path)

    assert after["vacancy:v1"]["content_hash"] != before["vacancy:v1"]["content_hash"]
    assert after["vacancy:v1"]["vector"] != before["vacancy:v1"]["vector"]

    assert after["v1-doc1"]["content_hash"] == before["v1-doc1"]["content_hash"]
    assert after["v1-doc1"]["vector"] == before["v1-doc1"]["vector"]
    assert after["v1-doc1"]["status"] == Status.APPLIED.value


@pytest.mark.embedding
def test_adding_one_document_adds_exactly_one_row(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)

    vacancy_dir = vault / "acme" / "v1"
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc3",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="Another note",
            date=date(2026, 1, 4),
        ),
        body="A brand new document added after the first build.",
    )

    report = build_index(read_vault(vault), index_path)

    assert report.added == 1
    assert "v1-doc3" in _rows_by_id(index_path)


@pytest.mark.embedding
def test_deleting_one_source_file_removes_exactly_one_row(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)

    (vault / "acme" / "v1" / "documents" / "v1-doc2.md").unlink()

    report = build_index(read_vault(vault), index_path)

    assert report.deleted == 1
    assert "v1-doc2" not in _rows_by_id(index_path)


@pytest.mark.embedding
def test_force_reembeds_every_row(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)

    report = build_index(read_vault(vault), index_path, force=True)

    total_rows = len(read_vault(vault).documents) + len(read_vault(vault).vacancies)
    assert report.changed == total_rows
    assert report.unchanged == 0


# --- Section 13: disposability -----------------------------------------


@pytest.mark.embedding
def test_deleting_index_and_rebuilding_reproduces_row_count_and_doc_ids(
    tmp_path: Path,
) -> None:
    vault = FIXTURE_VAULT
    snapshot = read_vault(vault)
    index_path = tmp_path / ".index"

    build_index(snapshot, index_path)
    before = _rows_by_id(index_path)
    before_count = len(before)
    before_ids = set(before)

    shutil.rmtree(index_path)
    build_index(snapshot, index_path)
    after = _rows_by_id(index_path)

    assert len(after) == before_count
    assert set(after) == before_ids


# --- Section 14: FTS ---------------------------------------------------


def _open_table(index_path: Path) -> lancedb.table.Table:
    return lancedb.connect(index_path).open_table("documents")


@pytest.mark.embedding
def test_fts_index_exists_after_first_build(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"

    build_index(read_vault(vault), index_path)

    indices = _open_table(index_path).list_indices()
    assert any(i.index_type == "FTS" and "text" in i.columns for i in indices)


@pytest.mark.embedding
def test_document_added_after_initial_build_is_searchable(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    build_index(read_vault(vault), index_path)

    vacancy_dir = vault / "acme" / "v1"
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc3",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="Unique note",
            date=date(2026, 1, 4),
        ),
        body="This mentions xylophonemarker, a very unique search term.",
    )
    build_index(read_vault(vault), index_path)

    table = _open_table(index_path)
    results = table.search("xylophonemarker", query_type="fts").to_list()
    assert any(r["doc_id"] == "v1-doc3" for r in results)


@pytest.mark.embedding
def test_rebuilding_does_not_duplicate_fts_entries(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    index_path = tmp_path / ".index"
    snapshot = read_vault(vault)

    build_index(snapshot, index_path)
    build_index(snapshot, index_path)
    build_index(snapshot, index_path)

    table = _open_table(index_path)
    results = table.search("promising", query_type="fts").to_list()
    assert len(results) == 1


# --- Section 15: resilience ----------------------------------------------


@pytest.mark.embedding
def test_snapshot_warnings_carry_into_index_report(tmp_path: Path) -> None:
    vault = _small_vault(tmp_path)
    snapshot = read_vault(vault)
    injected = snapshot.model_copy(
        update={"warnings": (*snapshot.warnings, _fake_warning())}
    )
    index_path = tmp_path / ".index"

    report = build_index(injected, index_path)

    assert any(w.kind == "fake_preexisting_warning" for w in report.warnings)


@pytest.mark.embedding
def test_vanished_source_file_is_skipped_with_warning_not_a_crash(
    tmp_path: Path,
) -> None:
    vault = _small_vault(tmp_path)
    snapshot = read_vault(vault)
    index_path = tmp_path / ".index"

    (vault / "acme" / "v1" / "documents" / "v1-doc1.md").unlink()

    report = build_index(snapshot, index_path)  # must not raise

    assert report.skipped >= 1
    assert any(w.kind == "vanished_source" for w in report.warnings)


# --- Section 16: performance -------------------------------------------

MIN_PERFORMANCE_VACANCY_COUNT = 500
BUILD_TIME_BUDGET_SECONDS = 240
REBUILD_TIME_BUDGET_SECONDS = 30


@pytest.fixture(scope="module")
def large_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    vault = tmp_path_factory.mktemp("large-perf-vault")
    generate_vault(vault, seed=20260101, min_companies=340, max_companies=360)
    return vault


@pytest.mark.embedding
def test_full_build_over_large_vault_completes_within_minutes(
    large_vault: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    snapshot = read_vault(large_vault)
    assert len(snapshot.vacancies) >= MIN_PERFORMANCE_VACANCY_COUNT

    index_path = tmp_path_factory.mktemp("large-perf-index") / ".index"

    report = build_index(snapshot, index_path)

    assert report.elapsed < BUILD_TIME_BUDGET_SECONDS


@pytest.mark.embedding
def test_no_change_rebuild_over_large_vault_completes_within_seconds(
    large_vault: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    snapshot = read_vault(large_vault)
    index_path = tmp_path_factory.mktemp("large-perf-index-2") / ".index"
    build_index(snapshot, index_path)

    report = build_index(snapshot, index_path)

    assert report.added == 0
    assert report.changed == 0
    assert report.elapsed < REBUILD_TIME_BUDGET_SECONDS
