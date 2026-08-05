from pathlib import Path

from vacancy_radar.vault.paths import (
    company_markdown_path,
    documents_dir,
    is_within,
    iter_vault_dirs,
    sidecar_path_for,
    vacancy_markdown_path,
)

FIXTURE_VAULT = Path(__file__).parent.parent / "fixtures" / "vault"


def test_company_markdown_path_matches_fixture_layout() -> None:
    path = company_markdown_path(FIXTURE_VAULT, "acme-corp")

    assert path == FIXTURE_VAULT / "acme-corp" / "_company.md"
    assert path.is_file()


def test_vacancy_markdown_and_documents_dir_match_fixture_layout() -> None:
    vacancy_dirname = "2022-03-22-acme-corp-backend-engineer"

    vacancy_path = vacancy_markdown_path(FIXTURE_VAULT, "acme-corp", vacancy_dirname)
    docs = documents_dir(FIXTURE_VAULT, "acme-corp", vacancy_dirname)

    assert vacancy_path == (
        FIXTURE_VAULT / "acme-corp" / vacancy_dirname / "vacancy.md"
    )
    assert vacancy_path.is_file()
    assert docs == FIXTURE_VAULT / "acme-corp" / vacancy_dirname / "documents"
    assert docs.is_dir()


def test_is_within_rejects_dotdot_escape(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    escaping = vault / ".." / "outside.md"

    assert not is_within(vault, escaping)


def test_is_within_rejects_symlink_pointing_outside(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = vault / "escape-link"
    link.symlink_to(outside, target_is_directory=True)

    assert not is_within(vault, link)


def test_is_within_accepts_ordinary_in_vault_path(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "company").mkdir(parents=True)
    real_file = vault / "company" / "_company.md"
    real_file.write_text("x", encoding="utf-8")

    assert is_within(vault, real_file)


def test_symlink_loop_terminates(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    child = vault / "child"
    child.mkdir()
    loop_link = child / "loop-back-to-vault"
    loop_link.symlink_to(vault, target_is_directory=True)

    # If this doesn't terminate, the test itself hangs.
    visited = list(iter_vault_dirs(vault))

    assert vault in visited
    assert child in visited


def test_sidecar_path_for_appends_md_to_the_full_filename() -> None:
    source = Path("/vault/acme/v1/documents/spec.pdf")

    assert sidecar_path_for(source) == Path("/vault/acme/v1/documents/spec.pdf.md")


def test_sidecar_path_for_distinct_sources_sharing_a_stem() -> None:
    docs_dir = Path("/vault/acme/v1/documents")

    pdf_sidecar = sidecar_path_for(docs_dir / "notes.pdf")
    docx_sidecar = sidecar_path_for(docs_dir / "notes.docx")

    assert pdf_sidecar == docs_dir / "notes.pdf.md"
    assert docx_sidecar == docs_dir / "notes.docx.md"
    assert pdf_sidecar != docx_sidecar
