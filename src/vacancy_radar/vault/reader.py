"""Reading a vault directory into an in-memory VaultSnapshot.

`read_vault` never raises on a malformed *file* - only `config.py`'s
`resolve_vault_path` raises on a missing or misconfigured *vault*.
Every file-level failure becomes a `VaultWarning` instead, so one
hand-edited file with broken YAML never takes an entire read down.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, ValidationError

from vacancy_radar.frontmatter import FrontmatterError, parse
from vacancy_radar.models import Company, Document, DocumentKind, Vacancy
from vacancy_radar.vault.hashing import content_hash
from vacancy_radar.vault.paths import (
    COMPANY_FILENAME,
    DOCUMENTS_DIRNAME,
    VACANCY_FILENAME,
    is_skipped_name,
    is_within,
    iter_vault_dirs,
)


class VaultWarning(BaseModel):
    """A non-fatal problem found while reading the vault.

    Warnings are data, not log calls - `vacancy-radar doctor` (a later
    stage) is the sole renderer. Nothing in this module writes to
    stdout or stderr.
    """

    model_config = ConfigDict(frozen=True)

    kind: str
    message: str
    paths: tuple[Path, ...] = ()


class VaultSnapshot(BaseModel):
    """An immutable, in-memory read of a vault at one point in time.

    Frozen, and its dict-shaped fields are `MappingProxyType` (not
    plain `dict`) so no caller can mutate a snapshot's contents in
    place - stage 3 diffs two snapshots to decide what to re-embed,
    and a mutable snapshot would make that comparison unreliable.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    vacancies: MappingProxyType[str, Vacancy]
    documents: MappingProxyType[str, Document]
    companies: MappingProxyType[str, Company]
    hashes: MappingProxyType[Path, str]
    vacancy_paths: MappingProxyType[str, Path]
    document_paths: MappingProxyType[str, Path]
    warnings: tuple[VaultWarning, ...] = ()

    def documents_for(self, vacancy_id: str) -> list[Document]:
        """That vacancy's documents, date-ascending, stable for ties."""
        matches = [d for d in self.documents.values() if d.vacancy_id == vacancy_id]
        return sorted(matches, key=lambda d: d.date)

    def vacancies_for(self, company_slug: str) -> list[Vacancy]:
        """That company's vacancies (empty list if it has none)."""
        return [v for v in self.vacancies.values() if v.company_slug == company_slug]

    def last_activity(self, vacancy_id: str) -> date:
        """The staleness anchor: most recent document date, falling
        back to `applied_date`, then `found_date`."""
        documents = self.documents_for(vacancy_id)
        if documents:
            return documents[-1].date
        vacancy = self.vacancies[vacancy_id]
        return vacancy.applied_date or vacancy.found_date


@dataclass
class _Documents:
    """Documents collected so far, alongside each one's file path."""

    by_id: dict[str, Document] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)

    def add(self, document: Document, path: Path) -> None:
        self.by_id[document.id] = document
        self.paths[document.id] = path


def read_vault(vault: Path) -> VaultSnapshot:
    """Traverse `vault` and return an immutable `VaultSnapshot`.

    See the module docstring for the resilience guarantee: a malformed
    file produces a `VaultWarning`, never an exception.
    """
    hashes = _hash_all_files(vault)

    companies: dict[str, Company] = {}
    documents = _Documents()
    warnings: list[VaultWarning] = []
    pending_vacancies: list[tuple[Path, Vacancy]] = []

    for company_path in _listdirs(vault, vault):
        slug = company_path.name
        company = _read_company(company_path, warnings)
        if company is not None:
            companies[slug] = company

        for vacancy_path in _listdirs(company_path, vault):
            _read_vacancy_dir(
                vault, vacancy_path, warnings, pending_vacancies, documents
            )

    vacancies, vacancy_paths = _resolve_duplicates(pending_vacancies, warnings)
    _warn_missing_companies(vacancies, companies, warnings)

    return VaultSnapshot(
        vacancies=MappingProxyType(vacancies),
        documents=MappingProxyType(documents.by_id),
        companies=MappingProxyType(companies),
        hashes=MappingProxyType(hashes),
        vacancy_paths=MappingProxyType(vacancy_paths),
        document_paths=MappingProxyType(documents.paths),
        warnings=tuple(warnings),
    )


def _listdirs(parent: Path, vault: Path) -> list[Path]:
    """Immediate subdirectories of `parent`, sorted, filtered to the
    ones traversal should visit (not dotfiles/internal, contained)."""
    return sorted(
        p
        for p in parent.iterdir()
        if p.is_dir() and not is_skipped_name(p.name) and is_within(vault, p)
    )


def _read_vacancy_dir(
    vault: Path,
    vacancy_path: Path,
    warnings: list[VaultWarning],
    pending_vacancies: list[tuple[Path, Vacancy]],
    documents: _Documents,
) -> None:
    vacancy_md = vacancy_path / VACANCY_FILENAME
    docs_dir = vacancy_path / DOCUMENTS_DIRNAME

    if not vacancy_md.is_file():
        if docs_dir.is_dir():
            warnings.append(
                VaultWarning(
                    kind="orphan_documents",
                    message=f"{docs_dir} has no sibling {VACANCY_FILENAME}",
                    paths=(docs_dir,),
                )
            )
        return

    vacancy = _read_vacancy(vacancy_md, warnings)
    if vacancy is None:
        return
    pending_vacancies.append((vacancy_path, vacancy))

    if not docs_dir.is_dir():
        return
    doc_paths = sorted(
        p
        for p in docs_dir.iterdir()
        if p.is_file() and not is_skipped_name(p.name) and is_within(vault, p)
    )
    for doc_path in doc_paths:
        document = _read_document(doc_path, vacancy, warnings)
        if document is not None:
            documents.add(document, doc_path)


def _warn_missing_companies(
    vacancies: dict[str, Vacancy],
    companies: dict[str, Company],
    warnings: list[VaultWarning],
) -> None:
    warnings.extend(
        VaultWarning(
            kind="missing_company",
            message=(
                f"vacancy {vacancy.id!r} references company "
                f"{vacancy.company_slug!r}, which has no {COMPANY_FILENAME}"
            ),
        )
        for vacancy in vacancies.values()
        if vacancy.company_slug not in companies
    )


def _hash_all_files(vault: Path) -> dict[Path, str]:
    """Hash every non-skipped file under `vault`, exactly once each."""
    hashes: dict[Path, str] = {}
    for directory in iter_vault_dirs(vault):
        children = sorted(
            p
            for p in directory.iterdir()
            if p.is_file() and not is_skipped_name(p.name)
        )
        for child in children:
            try:
                hashes[child] = content_hash(child)
            except OSError:
                continue  # unreadable - the parse pass below warns about it
    return hashes


def _read_company(company_path: Path, warnings: list[VaultWarning]) -> Company | None:
    company_md = company_path / COMPANY_FILENAME
    if not company_md.is_file():
        return None
    try:
        text = company_md.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(
            VaultWarning(kind="unreadable", message=str(exc), paths=(company_md,))
        )
        return None
    try:
        metadata, _ = parse(text, filename=str(company_md))
        return Company(**metadata)
    except (FrontmatterError, ValidationError) as exc:
        warnings.append(
            VaultWarning(
                kind="malformed_company",
                message=f"{company_md}: {exc}",
                paths=(company_md,),
            )
        )
        return None


def _read_vacancy(vacancy_md: Path, warnings: list[VaultWarning]) -> Vacancy | None:
    try:
        text = vacancy_md.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(
            VaultWarning(kind="unreadable", message=str(exc), paths=(vacancy_md,))
        )
        return None
    try:
        metadata, _ = parse(text, filename=str(vacancy_md))
    except FrontmatterError as exc:
        warnings.append(
            VaultWarning(
                kind="malformed_frontmatter",
                message=f"{vacancy_md}: {exc}",
                paths=(vacancy_md,),
            )
        )
        return None
    try:
        return Vacancy(**metadata)
    except ValidationError as exc:
        warnings.append(
            VaultWarning(
                kind="invalid_vacancy",
                message=f"{vacancy_md}: {exc}",
                paths=(vacancy_md,),
            )
        )
        return None


def _read_document(
    doc_path: Path, vacancy: Vacancy, warnings: list[VaultWarning]
) -> Document | None:
    if doc_path.suffix != ".md":
        # A real take-home is often a PDF or a zip, not a note - register
        # it by path, with no frontmatter to parse and no reliable
        # metadata source, so kind/title/date fall back to plausible
        # defaults derived from the file and its owning vacancy. The id
        # is the full filename, not the stem: two sources differing only
        # by extension (notes.pdf, notes.docx) must not collide.
        return Document(
            id=doc_path.name,
            vacancy_id=vacancy.id,
            kind=DocumentKind.TAKEHOME,
            title=doc_path.name,
            date=vacancy.found_date,
        )

    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(
            VaultWarning(kind="unreadable", message=str(exc), paths=(doc_path,))
        )
        return None
    try:
        metadata, _ = parse(text, filename=str(doc_path))
    except FrontmatterError as exc:
        warnings.append(
            VaultWarning(
                kind="malformed_frontmatter",
                message=f"{doc_path}: {exc}",
                paths=(doc_path,),
            )
        )
        return None

    if "extracted_from" in metadata:
        _check_sidecar(doc_path, metadata, warnings)
        return None

    try:
        return Document(**metadata)
    except ValidationError as exc:
        warnings.append(
            VaultWarning(
                kind="invalid_document",
                message=f"{doc_path}: {exc}",
                paths=(doc_path,),
            )
        )
        return None


def _check_sidecar(
    sidecar_path: Path, metadata: object, warnings: list[VaultWarning]
) -> None:
    """A `.md` file whose frontmatter has `extracted_from` is a
    sidecar, not a `Document` - it shadows the source it names rather
    than contributing a row of its own. Warn (and stay excluded from
    `documents`) if that source doesn't match or doesn't exist."""
    extracted_from = str(metadata["extracted_from"])  # type: ignore[index]
    own_source_name = sidecar_path.stem  # "spec.pdf.md" -> "spec.pdf"

    if extracted_from != own_source_name:
        warnings.append(
            VaultWarning(
                kind="mismatched_sidecar",
                message=(
                    f"{sidecar_path}: extracted_from {extracted_from!r} "
                    f"does not match its own filename {own_source_name!r}"
                ),
                paths=(sidecar_path,),
            )
        )
        return

    if not (sidecar_path.parent / extracted_from).is_file():
        warnings.append(
            VaultWarning(
                kind="orphan_sidecar",
                message=f"{sidecar_path}: source {extracted_from!r} does not exist",
                paths=(sidecar_path,),
            )
        )


def _resolve_duplicates(
    pending: list[tuple[Path, Vacancy]], warnings: list[VaultWarning]
) -> tuple[dict[str, Vacancy], dict[str, Path]]:
    """Keep one vacancy per id, deterministically, warning on the rest.

    When two paths parse to the same id, the path that sorts first
    (lexically, as a string) survives - independent of directory-entry
    iteration order, which isn't guaranteed stable across platforms.

    Returns the surviving vacancies and, alongside, each survivor's
    `vacancy.md` path.
    """
    by_id: dict[str, list[tuple[Path, Vacancy]]] = {}
    for path, vacancy in pending:
        by_id.setdefault(vacancy.id, []).append((path, vacancy))

    survivors: dict[str, Vacancy] = {}
    survivor_paths: dict[str, Path] = {}
    for vacancy_id, entries in by_id.items():
        entries_sorted = sorted(entries, key=lambda entry: str(entry[0]))
        survivor_path, survivor = entries_sorted[0]
        survivors[vacancy_id] = survivor
        survivor_paths[vacancy_id] = survivor_path / VACANCY_FILENAME
        if len(entries_sorted) > 1:
            warnings.append(
                VaultWarning(
                    kind="duplicate_vacancy_id",
                    message=(
                        f"duplicate vacancy id {vacancy_id!r} in "
                        f"{len(entries_sorted)} files; kept {survivor_path}"
                    ),
                    paths=tuple(path for path, _ in entries_sorted),
                )
            )
    return survivors, survivor_paths
