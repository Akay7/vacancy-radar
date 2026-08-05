"""The canonical vault tree layout and containment safety.

This is the tree stage 1's fixture generator (`tests/fixtures/generate.py`)
actually writes, not the `vacancies/`-prefixed, kind-split tree
originally sketched for this stage — see design.md for the
reconciliation:

    {vault}/.vacancy-radar/                    vault marker (empty)
    {vault}/{company_slug}/_company.md
    {vault}/{company_slug}/{vacancy_dirname}/vacancy.md
    {vault}/{company_slug}/{vacancy_dirname}/documents/*

Every module in this change derives paths from the helpers here rather
than hard-coding directory names, so a future layout change touches
one file.
"""

from collections.abc import Iterator
from pathlib import Path

VAULT_MARKER_DIRNAME = ".vacancy-radar"
"""The directory `config.resolve_vault_path` requires at the vault root."""

COMPANY_FILENAME = "_company.md"
VACANCY_FILENAME = "vacancy.md"
DOCUMENTS_DIRNAME = "documents"


def vault_marker_path(vault: Path) -> Path:
    """The path a vault's marker directory must exist at."""
    return vault / VAULT_MARKER_DIRNAME


def company_dir(vault: Path, company_slug: str) -> Path:
    """The directory holding one company's `_company.md` and vacancies."""
    return vault / company_slug


def company_markdown_path(vault: Path, company_slug: str) -> Path:
    """The path to a company's `_company.md`."""
    return company_dir(vault, company_slug) / COMPANY_FILENAME


def vacancy_dir(vault: Path, company_slug: str, vacancy_dirname: str) -> Path:
    """The directory holding one vacancy's `vacancy.md` and `documents/`."""
    return company_dir(vault, company_slug) / vacancy_dirname


def vacancy_markdown_path(vault: Path, company_slug: str, vacancy_dirname: str) -> Path:
    """The path to a vacancy's `vacancy.md`."""
    return vacancy_dir(vault, company_slug, vacancy_dirname) / VACANCY_FILENAME


def documents_dir(vault: Path, company_slug: str, vacancy_dirname: str) -> Path:
    """The directory holding one vacancy's documents (all kinds mixed)."""
    return vacancy_dir(vault, company_slug, vacancy_dirname) / DOCUMENTS_DIRNAME


def sidecar_path_for(source_path: Path) -> Path:
    """The path of the sidecar that would shadow `source_path`.

    The sidecar's name is the source's full filename (extension
    included) plus `.md` - not the stem - so two sources differing
    only by extension (`notes.pdf`, `notes.docx`) get independent
    sidecars instead of colliding on one `notes.md`.
    """
    return source_path.with_name(source_path.name + ".md")


def is_skipped_name(name: str) -> bool:
    """True for dotfiles and internal directories traversal must ignore.

    Covers `.git/`, `.index/`, and `.vacancy-radar/` (all dot-prefixed)
    along with any other dotfile a human or tool drops in the vault.
    """
    return name.startswith(".")


def is_within(vault: Path, path: Path) -> bool:
    """True iff `path`, resolved (symlinks followed, `..` collapsed),
    is `vault` itself or a descendant of it.

    Rejects both a lexical escape via `..` and a path that stays inside
    the vault lexically but is (or passes through) a symlink resolving
    outside it. Used by every read in this change before that read
    touches the filesystem.
    """
    resolved_vault = vault.resolve()
    resolved_path = path.resolve()
    return resolved_path == resolved_vault or resolved_path.is_relative_to(
        resolved_vault
    )


def iter_vault_dirs(root: Path) -> Iterator[Path]:
    """Yield `root` and every subdirectory beneath it, depth-first.

    Skips dotfiles and internal directories (`is_skipped_name`) and
    guards against symlink loops: a directory whose resolved real path
    was already visited in this walk is yielded once, at first
    encounter, and never descended into again.
    """
    visited: set[Path] = set()
    yield from _iter_vault_dirs(root, visited)


def _iter_vault_dirs(directory: Path, visited: set[Path]) -> Iterator[Path]:
    real = directory.resolve()
    if real in visited:
        return
    visited.add(real)
    yield directory

    children = sorted(
        child
        for child in directory.iterdir()
        if child.is_dir() and not is_skipped_name(child.name)
    )
    for child in children:
        yield from _iter_vault_dirs(child, visited)
