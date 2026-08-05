import sys
import time
from datetime import date
from pathlib import Path

import pytest

from vacancy_radar import frontmatter
from vacancy_radar.models import Company, Document, DocumentKind, Status, Vacancy
from vacancy_radar.vault import reader
from vacancy_radar.vault.paths import VAULT_MARKER_DIRNAME
from vacancy_radar.vault.reader import read_vault

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
if str(_FIXTURES_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_DIR))

from generate import generate_vault, write_broken_fixtures  # noqa: E402

FIXTURE_VAULT = _FIXTURES_DIR / "vault"
SEED = 20260101


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


def _write_document(vacancy_dir: Path, document: Document, body: str = "body") -> None:
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    metadata = document.model_dump(mode="json", exclude_none=True)
    (docs_dir / f"{document.id}.md").write_text(
        frontmatter.serialize(metadata, body), encoding="utf-8"
    )


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


def _write_sidecar(
    docs_dir: Path,
    source_name: str,
    *,
    extracted_from: str | None = None,
    body: str = "Extracted text from the source.",
) -> Path:
    """Write a sidecar for `source_name` (default: correctly matching
    it) into `docs_dir`. Pass `extracted_from` to build a mismatched
    sidecar."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "extracted_from": extracted_from if extracted_from is not None else source_name,
        "source_hash": "sha256:deadbeef",
        "extractor": "pypdf-6.14.2",
        "extracted_at": "2026-01-01",
        "manually_corrected": False,
    }
    sidecar_path = docs_dir / f"{source_name}.md"
    sidecar_path.write_text(frontmatter.serialize(metadata, body), encoding="utf-8")
    return sidecar_path


# --- Section 5: traversal and counts -----------------------------------


def test_reading_fixture_vault_yields_expected_counts() -> None:
    snapshot = read_vault(FIXTURE_VAULT)

    expected_vacancy_count = len(list(FIXTURE_VAULT.glob("*/*/vacancy.md")))
    expected_company_count = len(list(FIXTURE_VAULT.glob("*/_company.md")))
    expected_document_count = sum(
        1 for p in FIXTURE_VAULT.glob("*/*/documents/*") if p.is_file()
    )

    assert len(snapshot.vacancies) == expected_vacancy_count
    assert len(snapshot.companies) == expected_company_count
    assert len(snapshot.documents) == expected_document_count


def test_vacancy_id_matches_frontmatter_not_directory_name(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy = _simple_vacancy("the-real-id")
    _write_vacancy(vault, "acme", "totally-different-dirname", vacancy)

    snapshot = read_vault(vault)

    assert "the-real-id" in snapshot.vacancies
    assert "totally-different-dirname" not in snapshot.vacancies


def test_documents_attributed_to_containing_vacancy(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy = _simple_vacancy("v1")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", vacancy)
    _write_document(
        vacancy_dir,
        Document(
            id="v1-doc1",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="Note",
            date=date(2026, 1, 2),
        ),
    )

    snapshot = read_vault(vault)

    assert snapshot.documents["v1-doc1"].vacancy_id == "v1"


def test_company_with_no_vacancies_parses_with_empty_vacancy_list(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "lonely-corp", "Lonely Corp")

    snapshot = read_vault(vault)

    assert "lonely-corp" in snapshot.companies
    assert snapshot.vacancies_for("lonely-corp") == []


def test_non_markdown_document_is_registered_without_frontmatter_parsing(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy = _simple_vacancy("v1")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", vacancy)
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "assignment.pdf").write_bytes(b"%PDF fake take-home content")

    snapshot = read_vault(vault)

    assert "assignment.pdf" in snapshot.documents
    assert snapshot.documents["assignment.pdf"].vacancy_id == "v1"
    assert not any(
        "assignment.pdf" in str(path)
        for warning in snapshot.warnings
        for path in warning.paths
    )


def test_dotfiles_and_internal_directories_are_skipped(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")

    (vault / ".DS_Store").write_text("garbage", encoding="utf-8")
    (vault / ".git").mkdir()
    (vault / ".git" / "config").write_text("garbage", encoding="utf-8")
    (vault / ".index").mkdir()
    (vault / ".index" / "junk.bin").write_bytes(b"garbage")

    snapshot = read_vault(vault)

    assert not any(
        ".git" in str(path) or ".index" in str(path) or ".DS_Store" in str(path)
        for path in snapshot.hashes
    )
    assert snapshot.warnings == ()


# --- Section 6: resilience ----------------------------------------------


def _broken_vault(tmp_path_factory: pytest.TempPathFactory, name: str) -> Path:
    vault = tmp_path_factory.mktemp(name)
    generate_vault(vault, seed=SEED)
    write_broken_fixtures(vault)
    return vault


def test_malformed_yaml_warns_and_excludes_only_that_vacancy(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    healthy_vault = tmp_path_factory.mktemp("healthy-count")
    generate_vault(healthy_vault, seed=SEED)
    healthy_count = len(list(healthy_vault.glob("*/*/vacancy.md")))

    vault = _broken_vault(tmp_path_factory, "malformed-yaml")
    snapshot = read_vault(vault)

    assert any(
        w.kind == "malformed_frontmatter"
        and any("broken-yaml-vacancy" in str(p) for p in w.paths)
        for w in snapshot.warnings
    )
    assert "broken-yaml-vacancy" not in snapshot.vacancies
    assert len(snapshot.vacancies) >= healthy_count


def test_unknown_status_warns_and_excludes_vacancy(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _broken_vault(tmp_path_factory, "unknown-status")
    snapshot = read_vault(vault)

    assert any(
        w.kind == "invalid_vacancy"
        and any("unknown-status-vacancy" in str(p) for p in w.paths)
        for w in snapshot.warnings
    )
    assert "unknown-status-vacancy" not in snapshot.vacancies


def test_unreadable_file_warns_instead_of_crashing(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _broken_vault(tmp_path_factory, "unreadable")

    snapshot = read_vault(vault)  # must not raise

    assert any(
        w.kind == "unreadable" and any("unreadable-vacancy" in str(p) for p in w.paths)
        for w in snapshot.warnings
    )

    # Restore permissions so pytest's tmp_path cleanup can remove it.
    unreadable_path = (
        vault / "unreadable-vault-corp" / "unreadable-vacancy" / "vacancy.md"
    )
    unreadable_path.chmod(0o644)


def test_duplicate_vacancy_ids_produce_one_survivor_and_a_warning(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _broken_vault(tmp_path_factory, "duplicate-ids")
    snapshot = read_vault(vault)

    expected_duplicate_path_count = 2

    assert "duplicate-vacancy-id" in snapshot.vacancies
    matching = [w for w in snapshot.warnings if w.kind == "duplicate_vacancy_id"]
    assert len(matching) == 1
    assert len(matching[0].paths) == expected_duplicate_path_count

    # Reading again is deterministic - same survivor every time.
    snapshot2 = read_vault(vault)
    assert (
        snapshot.vacancies["duplicate-vacancy-id"].role
        == snapshot2.vacancies["duplicate-vacancy-id"].role
    )


def test_orphan_documents_directory_produces_a_warning(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    vault = _broken_vault(tmp_path_factory, "orphan")
    snapshot = read_vault(vault)

    assert any(
        w.kind == "orphan_documents"
        and any("orphan-vacancy" in str(p) for p in w.paths)
        for w in snapshot.warnings
    )
    assert not any(
        d.vacancy_id == "orphan-vacancy" for d in snapshot.documents.values()
    )


def test_vacancy_referencing_missing_company_still_loads_with_warning(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    # No _company.md written for "no-company-corp" - only a vacancy dir.
    vacancy = _simple_vacancy("orphan-company-vacancy", slug="no-company-corp")
    (vault / "no-company-corp").mkdir(parents=True)
    _write_vacancy(vault, "no-company-corp", "v1", vacancy)

    snapshot = read_vault(vault)

    assert "orphan-company-vacancy" in snapshot.vacancies
    assert any(w.kind == "missing_company" for w in snapshot.warnings)


# --- Section 7: hashing, change detection, immutability -----------------


def test_reading_twice_with_no_change_produces_identical_hash_maps(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))

    first = read_vault(vault)
    second = read_vault(vault)

    assert dict(first.hashes) == dict(second.hashes)


def test_editing_one_file_changes_exactly_one_hash_entry(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    _write_vacancy(vault, "acme", "v2", _simple_vacancy("v2"))

    before = dict(read_vault(vault).hashes)

    edited = vault / "acme" / "v1" / "vacancy.md"
    edited.write_text(edited.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    after = dict(read_vault(vault).hashes)

    changed = {k for k in before if before[k] != after.get(k)}
    assert changed == {edited}


def test_mutating_a_snapshot_collection_is_rejected(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))

    snapshot = read_vault(vault)

    with pytest.raises(TypeError):
        snapshot.vacancies["new-id"] = _simple_vacancy("new-id")


# --- Section 8: derived accessors ----------------------------------------


def test_last_activity_returns_most_recent_document_date(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    _write_document(
        vacancy_dir,
        Document(
            id="d1",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="d1",
            date=date(2026, 1, 5),
        ),
    )
    _write_document(
        vacancy_dir,
        Document(
            id="d2",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="d2",
            date=date(2026, 1, 9),
        ),
    )

    snapshot = read_vault(vault)

    assert snapshot.last_activity("v1") == date(2026, 1, 9)


def test_last_activity_falls_back_to_applied_date_with_no_documents(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy = _simple_vacancy(
        "v1", status=Status.APPLIED, applied_date=date(2026, 1, 3)
    )
    _write_vacancy(vault, "acme", "v1", vacancy)

    snapshot = read_vault(vault)

    assert snapshot.last_activity("v1") == date(2026, 1, 3)


def test_last_activity_falls_back_to_found_date_for_found_vacancy(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy = _simple_vacancy("v1", status=Status.FOUND, found_date=date(2026, 1, 1))
    _write_vacancy(vault, "acme", "v1", vacancy)

    snapshot = read_vault(vault)

    assert snapshot.last_activity("v1") == date(2026, 1, 1)


def test_documents_for_returns_ascending_date_order(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    _write_document(
        vacancy_dir,
        Document(
            id="d-late",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="late",
            date=date(2026, 1, 20),
        ),
    )
    _write_document(
        vacancy_dir,
        Document(
            id="d-early",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="early",
            date=date(2026, 1, 2),
        ),
    )

    snapshot = read_vault(vault)
    ordered = snapshot.documents_for("v1")

    assert [d.id for d in ordered] == ["d-early", "d-late"]


def test_documents_for_keeps_stable_order_for_same_date_documents(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    _write_document(
        vacancy_dir,
        Document(
            id="d-a",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="a",
            date=date(2026, 1, 5),
        ),
    )
    _write_document(
        vacancy_dir,
        Document(
            id="d-b",
            vacancy_id="v1",
            kind=DocumentKind.NOTE,
            title="b",
            date=date(2026, 1, 5),
        ),
    )

    snapshot = read_vault(vault)
    first_call = [d.id for d in snapshot.documents_for("v1")]
    second_call = [d.id for d in snapshot.documents_for("v1")]

    assert first_call == second_call


# --- Section 9: performance -----------------------------------------------

MIN_PERFORMANCE_VACANCY_COUNT = 500
PERFORMANCE_READ_BUDGET_SECONDS = 15


@pytest.fixture(scope="module")
def large_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    vault = tmp_path_factory.mktemp("large-perf-vault")
    generate_vault(vault, seed=SEED, min_companies=340, max_companies=360)
    return vault


def test_large_vault_reads_within_a_few_seconds(large_vault: Path) -> None:
    vacancy_count = len(list(large_vault.glob("*/*/vacancy.md")))
    assert vacancy_count >= MIN_PERFORMANCE_VACANCY_COUNT

    start = time.perf_counter()
    read_vault(large_vault)
    elapsed = time.perf_counter() - start

    assert elapsed < PERFORMANCE_READ_BUDGET_SECONDS


def test_large_vault_hashes_each_file_exactly_once(
    large_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_counts: dict[Path, int] = {}
    real_content_hash = reader.content_hash

    def counting_content_hash(path: Path) -> str:
        call_counts[path] = call_counts.get(path, 0) + 1
        return real_content_hash(path)

    monkeypatch.setattr(reader, "content_hash", counting_content_hash)

    snapshot = read_vault(large_vault)

    assert call_counts
    assert all(count == 1 for count in call_counts.values())
    assert set(call_counts) == set(snapshot.hashes)


# --- Sidecar recognition (index-build stage) ------------------------------


def test_source_with_matching_sidecar_registers_as_one_document_no_warning(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "spec.pdf").write_bytes(b"%PDF fake source bytes")
    _write_sidecar(docs_dir, "spec.pdf")

    snapshot = read_vault(vault)

    assert "spec.pdf" in snapshot.documents
    assert "spec.pdf.md" not in snapshot.documents
    assert snapshot.warnings == ()


def test_sidecar_frontmatter_never_reaches_document_validation(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    (docs_dir / "spec.pdf").parent.mkdir(parents=True, exist_ok=True)
    (docs_dir / "spec.pdf").write_bytes(b"%PDF fake source bytes")
    _write_sidecar(docs_dir, "spec.pdf")

    snapshot = read_vault(vault)

    assert not any(w.kind == "invalid_document" for w in snapshot.warnings)


def test_orphaned_sidecar_produces_a_warning_and_is_excluded(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    # No spec.pdf source present - the sidecar is orphaned.
    _write_sidecar(docs_dir, "spec.pdf")

    snapshot = read_vault(vault)

    assert any(
        w.kind == "orphan_sidecar" and any("spec.pdf.md" in str(p) for p in w.paths)
        for w in snapshot.warnings
    )
    assert not any(
        "spec.pdf.md" in doc.id or "spec.pdf.md" in doc.title
        for doc in snapshot.documents.values()
    )


def test_mismatched_sidecar_produces_a_warning_and_is_excluded(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "spec.pdf").write_bytes(b"%PDF fake source bytes")
    (docs_dir / "other.pdf").write_bytes(b"%PDF another fake source")
    _write_sidecar(docs_dir, "spec.pdf", extracted_from="other.pdf")

    snapshot = read_vault(vault)

    assert any(
        w.kind == "mismatched_sidecar" and any("spec.pdf.md" in str(p) for p in w.paths)
        for w in snapshot.warnings
    )


def test_same_stem_sources_get_independent_sidecars(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy_dir = _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))
    docs_dir = vacancy_dir / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "notes.pdf").write_bytes(b"%PDF fake pdf source")
    (docs_dir / "notes.docx").write_bytes(b"fake docx source bytes")
    _write_sidecar(docs_dir, "notes.pdf")
    _write_sidecar(docs_dir, "notes.docx")

    snapshot = read_vault(vault)

    assert "notes.pdf" in snapshot.documents
    assert "notes.docx" in snapshot.documents
    assert snapshot.warnings == ()


def test_ordinary_document_without_extracted_from_is_unaffected(
    tmp_path: Path,
) -> None:
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
    )

    snapshot = read_vault(vault)

    assert "v1-doc1" in snapshot.documents
    assert snapshot.warnings == ()


# --- Path lookups (index-build stage) --------------------------------------


def test_document_paths_maps_document_id_to_its_actual_file_path(
    tmp_path: Path,
) -> None:
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
    )

    snapshot = read_vault(vault)

    assert (
        snapshot.document_paths["v1-doc1"] == vacancy_dir / "documents" / "v1-doc1.md"
    )


def test_vacancy_paths_maps_vacancy_id_to_its_vacancy_md_path(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    vacancy = _simple_vacancy("the-real-id")
    vacancy_dir = _write_vacancy(vault, "acme", "some-dirname", vacancy)

    snapshot = read_vault(vault)

    assert snapshot.vacancy_paths["the-real-id"] == vacancy_dir / "vacancy.md"


def test_path_mappings_are_immutable(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _init_vault(vault)
    _write_company(vault, "acme", "Acme")
    _write_vacancy(vault, "acme", "v1", _simple_vacancy("v1"))

    snapshot = read_vault(vault)

    with pytest.raises(TypeError):
        snapshot.document_paths["new"] = Path("/nonexistent")
    with pytest.raises(TypeError):
        snapshot.vacancy_paths["new"] = Path("/nonexistent")
