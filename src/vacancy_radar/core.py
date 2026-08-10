"""Business-logic entry points shared by the CLI and, later, the MCP
server (stage 8) - see design.md decision 1 (invariant 4: every
read/write a caller needs lives here exactly once, never duplicated
inside a CLI command or an MCP tool).

Every function resolves its own vault (an explicit `vault` argument, or
`VAULT_PATH`, via `config.resolve_vault_path` - the same precedence
`search()` and `doctor()` use) and reads it fresh via
`vault.reader.read_vault`.

The read half (`resolve`, `list_vacancies`, `get_company`,
`get_vacancy`, `read_document`, `search`, `doctor`) never writes
anything. The write half (`append_note`, `set_status`, `add_document`,
`reindex`, `create_vacancy` - stage 7's `cli-write` change) is either
strictly append-only at the filesystem level or a validated, typed-
error-guarded update confined to `vacancy.md`'s frontmatter and its
status-history block - invariant 3, enforced here in code. See
`cli-write`'s design.md for the write half's decisions: derived
filenames (never caller-supplied), `external_id` dedupe, eager
reindex-on-write, the status graph as data in `models.py`, and the
atomic-write strategy every write in this module goes through.
"""

import difflib
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from vacancy_radar import frontmatter
from vacancy_radar.config import resolve_target_path, resolve_vault_path
from vacancy_radar.ids import new_vacancy_id, slugify
from vacancy_radar.index import search as index_search
from vacancy_radar.index.build import TABLE_NAME, IndexReport, build_index
from vacancy_radar.index.embed import DEFAULT_EMBEDDING_MODEL_NAME, vector_dim
from vacancy_radar.index.store import IndexHandle, default_index_path, get_index_handle
from vacancy_radar.models import (
    STATUS_TRANSITIONS,
    Company,
    Document,
    DocumentKind,
    Status,
    Vacancy,
)
from vacancy_radar.vault.paths import (
    DOCUMENTS_DIRNAME,
    company_dir,
    company_markdown_path,
    is_within,
    vacancy_markdown_path,
    vault_marker_path,
)
from vacancy_radar.vault.reader import VaultSnapshot, read_vault

DEFAULT_LIST_LIMIT = 50
NEEDS_REVIEW_TAG = "needs_review"
FUZZY_MATCH_CUTOFF = 0.6
"""`resolve`'s fuzzy tier's `difflib.get_close_matches` cutoff - tuned
against the fixture vault's company names (see design.md's Open
Questions): loose enough for "Acme" to reach "Acme Corp", tight enough
that unrelated company names don't spuriously collide."""


class CoreError(Exception):
    """Base class for every typed error `core.py` raises."""


class EntityNotFoundError(CoreError):
    """Raised when a query matches no vacancy, no company, at any tier."""

    def __init__(self, query: str) -> None:
        self.query = query
        super().__init__(f"nothing in the vault matches {query!r}")


class AmbiguousEntityError(CoreError):
    """Raised when a query matches more than one company - see
    design.md decision 3: `resolve` never guesses, so a caller that
    demands a single entity (`get_company`, `get_vacancy`,
    `list_vacancies`'s `company` filter) raises instead of picking."""

    def __init__(
        self, query: str, candidates: "tuple[ResolutionCandidate, ...]"
    ) -> None:
        self.query = query
        self.candidates = candidates
        names = ", ".join(f"{c.name} ({c.slug})" for c in candidates)
        super().__init__(f"{query!r} matches more than one company: {names}")


class WrongEntityKindError(CoreError):
    """Raised when a query resolves unambiguously, but to the other
    kind of entity than the caller asked for (e.g. `get_vacancy` given
    a query that names a company)."""

    def __init__(self, query: str, *, expected: str, resolved: str) -> None:
        self.query = query
        self.expected = expected
        self.resolved = resolved
        super().__init__(f"{query!r} resolved to a {resolved}, not a {expected}")


class PathOutsideVaultError(CoreError):
    """Raised by `read_document` for a path resolving outside the vault
    - reuses `vault.paths.is_within`, the stage 2 containment check."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} is outside the vault")


class DocumentNotFoundError(CoreError):
    """Raised by `read_document` for a path inside the vault that does
    not exist, or is not a file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} does not exist or is not a file")


class VaultTargetIsAFileError(CoreError):
    """Raised by `init_vault` when its target path exists as a regular
    file rather than a directory - no filesystem change is made."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} exists and is not a directory")


# --- Vault initialization ------------------------------------------------


@dataclass(frozen=True)
class VaultInitResult:
    """`init_vault`'s result: the vault's (absolute) path, and whether
    this call created it. `created` is `False` exactly when the target
    was already a valid vault before this call - `init_vault` is
    idempotent, never destructive (design.md decision 3)."""

    path: Path
    created: bool


def init_vault(path: str | Path | None = None) -> VaultInitResult:
    """Create a vault at `path` (or `VAULT_PATH` when `path` is
    omitted), via `config.resolve_target_path`'s explicit-then-
    `VAULT_PATH` precedence - the same precedence every other `core.py`
    function uses, without requiring the target to already exist
    (unlike `resolve_vault_path`, which every other function relies on).

    Idempotent: creates the target directory (and any missing parents)
    and its `.vacancy-radar/` marker in one step when neither exists
    yet; adds just the marker to an existing, non-vault directory,
    touching nothing else already there; is a no-op, `created=False`,
    when the target is already a valid vault. Raises
    `VaultTargetIsAFileError`, with no filesystem change, when the
    target exists as a file. See design.md decisions 3-4."""
    target = resolve_target_path(path)

    if target.exists() and not target.is_dir():
        raise VaultTargetIsAFileError(target)

    marker = vault_marker_path(target)
    if marker.is_dir():
        return VaultInitResult(path=target, created=False)

    marker.mkdir(parents=True, exist_ok=True)
    return VaultInitResult(path=target, created=True)


# --- Resolution --------------------------------------------------------


@dataclass(frozen=True)
class ResolutionCandidate:
    """One ambiguous company match `resolve` couldn't pick between."""

    slug: str
    name: str


@dataclass(frozen=True)
class Resolution:
    """The outcome of one `resolve` call.

    Exactly one of `vacancy_id`/`company_slug` is set on a resolved
    match; both are `None` and `candidates` lists every ambiguous
    match when `resolve` can't pick; all three are empty/`None` when
    nothing matched. `resolve` never raises and never guesses (design.md
    decision 3) - a caller that needs a single entity is the one that
    turns "ambiguous" or "not found" into a typed error.
    """

    vacancy_id: str | None = None
    company_slug: str | None = None
    candidates: tuple[ResolutionCandidate, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.vacancy_id is not None or self.company_slug is not None


def resolve(query: str, vault: Path | None = None) -> Resolution:
    """Resolve `query` against the vault: exact vacancy id, then exact
    company slug, then a unique case-insensitive company-name match,
    then a unique fuzzy company-name match - stopping at the first
    tier that matches exactly one entity (design.md decision 3)."""
    snapshot = read_vault(resolve_vault_path(vault))
    return _resolve(query, snapshot)


def _resolve(query: str, snapshot: VaultSnapshot) -> Resolution:
    if query in snapshot.vacancies:
        return Resolution(vacancy_id=query)

    registry = _company_registry(snapshot)
    if query in registry:
        return Resolution(company_slug=query)

    matches = _company_name_matches(query, registry)
    return _resolution_from_matches(matches, registry)


def _company_name_matches(query: str, registry: dict[str, str]) -> list[str]:
    """Company slugs matching `query` by display name: a unique tier of
    exact case-insensitive matches when any exist, else the fuzzy
    tier - never both at once (design.md decision 3's tier order)."""
    lowered = query.strip().lower()
    exact_ci = [slug for slug, name in registry.items() if name.lower() == lowered]
    if exact_ci:
        return exact_ci
    return _fuzzy_company_matches(query, registry)


def _resolution_from_matches(
    matches: list[str], registry: dict[str, str]
) -> Resolution:
    if len(matches) == 1:
        return Resolution(company_slug=matches[0])
    if len(matches) > 1:
        return Resolution(candidates=_candidates(matches, registry))
    return Resolution()


def _company_registry(snapshot: VaultSnapshot) -> dict[str, str]:
    """Every company slug the vault knows about, mapped to a display
    name - from `_company.md` when present, else the first vacancy
    that references the slug. A company directory with vacancies but
    no `_company.md` must still be resolvable (see the company-dossier
    spec's missing-file scenario)."""
    registry = {c.slug: c.name for c in snapshot.companies.values()}
    for vacancy in snapshot.vacancies.values():
        registry.setdefault(vacancy.company_slug, vacancy.company)
    return registry


def _candidates(
    slugs: Iterable[str], registry: dict[str, str]
) -> tuple[ResolutionCandidate, ...]:
    return tuple(
        ResolutionCandidate(slug=slug, name=registry[slug]) for slug in sorted(slugs)
    )


def _fuzzy_company_matches(query: str, registry: dict[str, str]) -> list[str]:
    by_name: dict[str, str] = {}
    for slug, name in registry.items():
        by_name.setdefault(name, slug)
    matches = difflib.get_close_matches(
        query, list(by_name), n=len(by_name), cutoff=FUZZY_MATCH_CUTOFF
    )
    return [by_name[name] for name in matches]


def _resolve_company_slug(query: str, snapshot: VaultSnapshot) -> str:
    resolution = _resolve(query, snapshot)
    if resolution.company_slug is not None:
        return resolution.company_slug
    if resolution.vacancy_id is not None:
        raise WrongEntityKindError(query, expected="company", resolved="vacancy")
    if resolution.candidates:
        raise AmbiguousEntityError(query, resolution.candidates)
    raise EntityNotFoundError(query)


def _resolve_vacancy_id(query: str, snapshot: VaultSnapshot) -> str:
    resolution = _resolve(query, snapshot)
    if resolution.vacancy_id is not None:
        return resolution.vacancy_id
    if resolution.company_slug is not None:
        raise WrongEntityKindError(query, expected="vacancy", resolved="company")
    if resolution.candidates:
        raise AmbiguousEntityError(query, resolution.candidates)
    raise EntityNotFoundError(query)


# --- Listing -------------------------------------------------------------


class VacancySummary(BaseModel):
    """One `list_vacancies` row: compact and bounded by construction -
    no document body or path, ever (see the vacancy-listing spec)."""

    id: str
    company: str
    role: str
    status: Status
    applied_date: date | None = None
    last_activity: date
    document_count: int


def list_vacancies(  # noqa: PLR0913 - the deliverable's public signature; each is meaningful
    *,
    status: list[Status] | None = None,
    company: str | None = None,
    since: date | None = None,
    stale_days: int | None = None,
    needs_review: bool = False,
    limit: int = DEFAULT_LIST_LIMIT,
    sort: str = "activity",
    vault: Path | None = None,
) -> list[VacancySummary]:
    """The filtered, sorted, bounded dashboard query over vacancy
    summaries. `stale_days` filters on `last_activity` (the vault's
    most-recent-document-or-fallback date), not `applied_date` - an
    application from long ago with a recent document is not stale
    (see the vacancy-listing spec)."""
    snapshot = read_vault(resolve_vault_path(vault))
    vacancies = list(snapshot.vacancies.values())

    if status:
        wanted = set(status)
        vacancies = [v for v in vacancies if v.status in wanted]
    if company is not None:
        slug = _resolve_company_slug(company, snapshot)
        vacancies = [v for v in vacancies if v.company_slug == slug]
    if since is not None:
        vacancies = [v for v in vacancies if (v.applied_date or v.found_date) >= since]
    if needs_review:
        vacancies = [v for v in vacancies if NEEDS_REVIEW_TAG in v.tags]
    if stale_days is not None:
        # Local calendar day, not UTC's - this is a local-first personal
        # tool, and "today" should match the day the user is actually
        # living in, not whatever day it happens to be at Greenwich.
        today = datetime.now().astimezone().date()
        cutoff = today - timedelta(days=stale_days)
        vacancies = [v for v in vacancies if snapshot.last_activity(v.id) <= cutoff]

    summaries = [_vacancy_summary(v.id, snapshot) for v in vacancies]

    if sort == "activity":
        summaries.sort(key=lambda s: (-s.last_activity.toordinal(), s.id))

    return summaries[:limit]


def _vacancy_summary(vacancy_id: str, snapshot: VaultSnapshot) -> VacancySummary:
    vacancy = snapshot.vacancies[vacancy_id]
    return VacancySummary(
        id=vacancy.id,
        company=vacancy.company,
        role=vacancy.role,
        status=vacancy.status,
        applied_date=vacancy.applied_date,
        last_activity=snapshot.last_activity(vacancy.id),
        document_count=len(snapshot.documents_for(vacancy.id)),
    )


# --- Company dossier -------------------------------------------------------


class CompanyDossier(BaseModel):
    """`get_company`'s bounded, cross-time view of one company: every
    vacancy (as a `VacancySummary` - counts and paths, never document
    bodies), recruiters/domains/notes from `_company.md` when present."""

    slug: str
    name: str
    domains: list[str] = Field(default_factory=list)
    recruiters: list[str] = Field(default_factory=list)
    notes: str | None = None
    vacancies: list[VacancySummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def get_company(name: str, vault: Path | None = None) -> CompanyDossier:
    """Every vacancy for the company `name` resolves to, spanning the
    vault's oldest and newest records, plus `_company.md`'s recruiters/
    domains/notes when present. Succeeds (with a warning) for a company
    directory that has vacancies but no `_company.md` - never raises
    for that (see the company-dossier spec)."""
    snapshot = read_vault(resolve_vault_path(vault))
    slug = _resolve_company_slug(name, snapshot)

    vacancies = sorted(
        snapshot.vacancies_for(slug),
        key=lambda v: (v.applied_date or v.found_date, v.id),
    )
    summaries = [_vacancy_summary(v.id, snapshot) for v in vacancies]

    company = snapshot.companies.get(slug)
    if company is None:
        display_name = vacancies[0].company if vacancies else slug
        return CompanyDossier(
            slug=slug,
            name=display_name,
            vacancies=summaries,
            warnings=[f"{slug!r} has no _company.md"],
        )

    return CompanyDossier(
        slug=company.slug,
        name=company.name,
        domains=list(company.domains),
        recruiters=list(company.recruiters),
        notes=company.notes,
        vacancies=summaries,
    )


# --- Vacancy detail --------------------------------------------------------


class DocumentSummary(BaseModel):
    """One document's metadata in a `VacancyDetail` - path and title
    only, never its body (see the vacancy-detail spec)."""

    id: str
    title: str
    kind: DocumentKind
    date: date
    path: str


class VacancyDetail(BaseModel):
    """One vacancy's full record: frontmatter, `stage_note` verbatim,
    and its documents as bounded `DocumentSummary` rows - no document
    bodies (see the vacancy-detail spec)."""

    id: str
    company: str
    company_slug: str
    role: str
    status: Status
    source_url: str
    found_date: date
    applied_date: date | None = None
    stage_note: str | None = None
    salary_note: str | None = None
    recruiter: str | None = None
    external_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    documents: list[DocumentSummary] = Field(default_factory=list)


def get_vacancy(id_or_query: str, vault: Path | None = None) -> VacancyDetail:
    """One vacancy's full frontmatter, `stage_note`, and document index
    (paths and titles, date-ascending) - never document bodies."""
    snapshot = read_vault(resolve_vault_path(vault))
    vacancy_id = _resolve_vacancy_id(id_or_query, snapshot)
    vacancy = snapshot.vacancies[vacancy_id]

    documents = [
        DocumentSummary(
            id=d.id,
            title=d.title,
            kind=d.kind,
            date=d.date,
            path=str(snapshot.document_paths[d.id]),
        )
        for d in snapshot.documents_for(vacancy_id)
    ]

    return VacancyDetail(
        id=vacancy.id,
        company=vacancy.company,
        company_slug=vacancy.company_slug,
        role=vacancy.role,
        status=vacancy.status,
        source_url=vacancy.source_url,
        found_date=vacancy.found_date,
        applied_date=vacancy.applied_date,
        stage_note=vacancy.stage_note,
        salary_note=vacancy.salary_note,
        recruiter=vacancy.recruiter,
        external_id=vacancy.external_id,
        tags=list(vacancy.tags),
        documents=documents,
    )


# --- Reading a document ----------------------------------------------------


class DocumentContent(BaseModel):
    """The full text of one vault file, per `read_document`."""

    path: str
    text: str


def read_document(path: Path | str, vault: Path | None = None) -> DocumentContent:
    """Full text of the file at `path`, which may be absolute or
    vault-relative. Rejects any path resolving outside the vault
    (including via `..`), using `vault.paths.is_within` - the same
    containment check every other read in this codebase uses."""
    vault_root = resolve_vault_path(vault)
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = vault_root / candidate

    if not is_within(vault_root, candidate):
        raise PathOutsideVaultError(candidate)
    if not candidate.is_file():
        raise DocumentNotFoundError(candidate)

    text = candidate.read_text(encoding="utf-8")
    return DocumentContent(path=str(candidate), text=text)


# --- Index freshness --------------------------------------------------------


def _vacancy_row_id(vacancy_id: str) -> str:
    """Mirrors `index.build._vacancy_row_id`'s `"vacancy:{id}"` scheme -
    duplicated rather than imported, since that helper is private to
    `index.build`."""
    return f"vacancy:{vacancy_id}"


@dataclass(frozen=True)
class IndexFreshnessWarning:
    """A degraded-not-blocked signal (design.md decision 4): the index
    is missing some vault documents, but the caller still gets an
    answer from whatever the index does have."""

    missing_count: int
    message: str


def _index_doc_ids(index: IndexHandle) -> set[str] | None:
    try:
        table = index.connection.open_table(TABLE_NAME)
    except (ValueError, FileNotFoundError):
        return None
    rows = table.search().select(["doc_id"]).to_arrow().to_pylist()
    return {row["doc_id"] for row in rows}


def _index_freshness(vault: Path, index: IndexHandle) -> IndexFreshnessWarning | None:
    """Compare the vault's current document set against what `index`'s
    table actually holds. Never raises - a missing table (index never
    built) and a missing row (index stale) both become a warning, or
    `None` when nothing is missing (design.md decision 4)."""
    snapshot = read_vault(vault)
    vault_ids = {_vacancy_row_id(vid) for vid in snapshot.vacancies} | set(
        snapshot.documents
    )

    indexed_ids = _index_doc_ids(index)
    if indexed_ids is None:
        if not vault_ids:
            return None
        return IndexFreshnessWarning(
            missing_count=len(vault_ids),
            message=(
                f"the index has not been built yet ({len(vault_ids)} vault "
                "document(s) not indexed) - fix by running build_index "
                "(index.build.build_index)"
            ),
        )

    missing_ids = vault_ids - indexed_ids
    if not missing_ids:
        return None
    return IndexFreshnessWarning(
        missing_count=len(missing_ids),
        message=(
            f"the index is missing {len(missing_ids)} vault document(s) - fix "
            "by running build_index (index.build.build_index) to refresh it"
        ),
    )


# --- Search ------------------------------------------------------------


@dataclass(frozen=True)
class SearchResults:
    """`core.search`'s return: `index.search.search`'s own hits and
    metadata, unchanged, plus an `index-freshness` warning attached
    without altering the hits themselves (design.md decision 4)."""

    hits: list[index_search.SearchHit]
    mode: index_search.SearchMode
    effective_vector_weight: float | None
    elapsed_ms: float
    total_candidates: int
    freshness_warning: IndexFreshnessWarning | None = None


def search(  # noqa: PLR0913 - mirrors index.search.search's own public signature
    query: str,
    *,
    vault: Path | None = None,
    mode: index_search.SearchMode | None = None,
    company_slug: str | None = None,
    status: list[Status] | None = None,
    kind: list[DocumentKind] | None = None,
    tags: list[str] | None = None,
    since: date | None = None,
    limit: int | None = None,
    vector_weight: float | None = None,
) -> SearchResults:
    """Resolve the vault and its index, delegate to
    `index.search.search` unchanged, and attach an `index-freshness`
    warning to the result - never raising for staleness itself (only
    `index.search.search`'s own typed errors propagate)."""
    vault_root = resolve_vault_path(vault)
    index = get_index_handle(vault_root)

    raw = index_search.search(
        index,
        query,
        mode=mode,
        company_slug=company_slug,
        status=status,
        kind=kind,
        tags=tags,
        since=since,
        limit=limit,
        vector_weight=vector_weight,
    )

    return SearchResults(
        hits=raw.hits,
        mode=raw.mode,
        effective_vector_weight=raw.effective_vector_weight,
        elapsed_ms=raw.elapsed_ms,
        total_candidates=raw.total_candidates,
        freshness_warning=_index_freshness(vault_root, index),
    )


# --- Doctor ------------------------------------------------------------


def _embedding_model_available(model_name: str) -> tuple[bool, str | None]:
    """Cheap availability check: `vector_dim` looks up `fastembed`'s
    static supported-model metadata rather than loading the model, so
    this never downloads anything (see `index.embed`'s docstring)."""
    try:
        vector_dim(model_name)
    except Exception as exc:  # noqa: BLE001 - reported as a doctor field, never raised
        return False, str(exc)
    return True, None


class DoctorReport(BaseModel):
    """`vacancy-radar doctor`'s composed health check: vault path,
    index presence/freshness, embedding-model availability, and every
    `VaultWarning` `read_vault` collected. Assembled here, not in
    `cli.py` (design.md decision 1) - an MCP `doctor` tool at stage 8
    calls this function unchanged."""

    vault_path: str
    index_present: bool
    index_fresh: bool
    freshness_message: str | None = None
    embedding_model_available: bool
    embedding_model_error: str | None = None
    vault_warnings: list[str] = Field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """False when anything other than index staleness/absence is
        wrong - those degrade (design.md decision 4), they never fail
        `doctor` on their own."""
        return self.embedding_model_available and not self.vault_warnings


def doctor(vault: Path | None = None) -> DoctorReport:
    """The vault's health: path, index presence/freshness, embedding-
    model availability, and every warning `read_vault` collected."""
    vault_root = resolve_vault_path(vault)
    snapshot = read_vault(vault_root)

    index_path = default_index_path(vault_root)
    index_present = index_path.is_dir()
    freshness_warning: IndexFreshnessWarning | None = None
    if index_present:
        freshness_warning = _index_freshness(vault_root, get_index_handle(vault_root))

    model_available, model_error = _embedding_model_available(
        DEFAULT_EMBEDDING_MODEL_NAME
    )

    return DoctorReport(
        vault_path=str(vault_root),
        index_present=index_present,
        index_fresh=index_present and freshness_warning is None,
        freshness_message=freshness_warning.message if freshness_warning else None,
        embedding_model_available=model_available,
        embedding_model_error=model_error,
        vault_warnings=[w.message for w in snapshot.warnings],
    )


# --- Writing: shared errors, atomic writes, filename derivation ------------


class DocumentAlreadyExistsError(CoreError):
    """Raised when a write would overwrite an existing vault file, or
    when filename-collision suffixing exhausts its attempts without
    finding a free path - append-only enforcement (invariant 3, see
    design.md decisions 2 and 9)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"{path} already exists and would not be overwritten")


_TEMP_SUFFIX = ".tmp"


def _atomic_write(path: Path, text: str, *, overwrite: bool) -> None:
    """Write `text` to `path` atomically: a dot-prefixed temp file
    created in `path`'s own directory, then `os.replace` (design.md
    decision 9). A reader sees either the prior complete file or the
    new complete file - never a truncated one - regardless of when a
    failure happens.

    `overwrite=False` is every new-file write's append-only guard: if
    `path` already exists, this raises `DocumentAlreadyExistsError`
    without creating a temp file or touching `path`. `overwrite=True`
    is `set_status`'s sole, explicit exception (`vacancy.md`'s
    frontmatter update) - it replaces `path`'s content but the write
    is still atomic.
    """
    if not overwrite and path.exists():
        raise DocumentAlreadyExistsError(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=_TEMP_SUFFIX, dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        tmp_path.replace(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _ensure_within_vault(vault: Path, path: Path) -> None:
    """Defense in depth alongside filename derivation (design.md
    decision 2): every write in this module checks this before
    touching the filesystem, even though a derived path can't
    lexically escape its target directory."""
    if not is_within(vault, path):
        raise PathOutsideVaultError(path)


MAX_TITLE_SLUG_LENGTH = 60
"""Mirrors `ids.MAX_ROLE_SLUG_LENGTH`'s role - keeps derived filenames
readable in a file browser rather than one long run of hyphens."""

_MAX_FILENAME_SUFFIX_ATTEMPTS = 500
"""A derived filename that collides this many times in the same
directory is treated as exhausted, not looped on forever."""


def _derive_document_filename(
    directory: Path, effective_date: date, kind: DocumentKind, title: str
) -> str:
    """A safe, derived `{date}-{kind}-{slug}.md` filename, collision-
    suffixed against `directory`'s actual contents (design.md decision
    2) - never a caller-supplied path. `ids.slugify` collapses `/`,
    `\\`, and `..` runs in `title` to hyphens, so no title can steer
    the result outside `directory`; `_ensure_within_vault` double-checks
    the final path anyway."""
    slug = slugify(title)[:MAX_TITLE_SLUG_LENGTH] or "untitled"
    base = f"{effective_date.isoformat()}-{kind.value}-{slug}"

    candidate = f"{base}.md"
    if not (directory / candidate).exists():
        return candidate

    for suffix in range(2, _MAX_FILENAME_SUFFIX_ATTEMPTS + 1):
        candidate = f"{base}-{suffix}.md"
        if not (directory / candidate).exists():
            return candidate

    raise DocumentAlreadyExistsError(directory / f"{base}.md")


# --- Writing: reindex() ------------------------------------------------


def reindex(*, force: bool = False, vault: Path | None = None) -> IndexReport:
    """Wrap stage 3's incremental `build_index` over a fresh
    `VaultSnapshot` (design.md decision 4). Every write function below
    calls this with `force=False` as its last step, before returning -
    the same call `vacancy-radar reindex` makes directly. Cheap when
    little changed: `build_index` diffs by content hash and re-embeds
    only what's new or changed."""
    vault_root = resolve_vault_path(vault)
    index_path = default_index_path(vault_root)
    return build_index(read_vault(vault_root), index_path, force=force)


# --- Writing: add_document() ------------------------------------------


def _document_by_external_id(
    snapshot: VaultSnapshot, vacancy_id: str, external_id: str
) -> Document | None:
    for document in snapshot.documents_for(vacancy_id):
        if document.external_id == external_id:
            return document
    return None


def add_document(  # noqa: PLR0913, PLR0917 - the deliverable's public signature; each is meaningful
    vacancy_id: str,
    kind: DocumentKind,
    content: str,
    title: str,
    date: date,
    external_id: str | None = None,
    *,
    vault: Path | None = None,
) -> Path:
    """File a document into `vacancy_id`'s single, flat `documents/`
    directory (design.md decision 1 - `kind` lives in frontmatter, not
    in a subdirectory). The filename is derived from `date`, `kind`,
    and `title` via `_derive_document_filename` - never from `content`
    or a caller-supplied path (design.md decision 2, the safety
    property stage 8 depends on). Refuses to overwrite an existing
    path.

    When `external_id` already matches a document filed under this
    vacancy, returns that document's existing path and writes nothing
    (design.md decision 3) - re-filing the same source is a no-op, not
    a duplicate. Refreshes the index before returning (design.md
    decision 4), so the filed document is immediately searchable.
    """
    vault_root = resolve_vault_path(vault)
    snapshot = read_vault(vault_root)

    if vacancy_id not in snapshot.vacancies:
        raise EntityNotFoundError(vacancy_id)

    if external_id is not None:
        existing = _document_by_external_id(snapshot, vacancy_id, external_id)
        if existing is not None:
            return snapshot.document_paths[existing.id]

    docs_dir = snapshot.vacancy_paths[vacancy_id].parent / DOCUMENTS_DIRNAME
    filename = _derive_document_filename(docs_dir, date, kind, title)
    target = docs_dir / filename
    _ensure_within_vault(vault_root, target)

    document = Document(
        id=target.stem,
        vacancy_id=vacancy_id,
        kind=kind,
        title=title,
        date=date,
        external_id=external_id,
    )
    metadata = document.model_dump(mode="json", exclude_none=True)
    text = frontmatter.serialize(metadata, content)
    _atomic_write(target, text, overwrite=False)

    reindex(vault=vault_root)
    return target


# --- Writing: append_note() ---------------------------------------------

NOTE_TITLE = "Note"
"""`append_note`'s fixed, derived title (design.md decision 2) - a
note's filename is never influenced by caller-supplied text."""


def append_note(
    vacancy_id: str, text: str, date: date | None = None, *, vault: Path | None = None
) -> Path:
    """Append a dated note to `vacancy_id`'s `documents/` directory.

    A thin call into `add_document` with `kind=DocumentKind.NOTE`, a
    fixed title, and `content=text` (design.md decision 2) - no
    duplicated filename-derivation logic. Never overwrites an existing
    note: a second note on the same day gets its own,
    collision-suffixed file. `date` defaults to today's local calendar
    day, matching `list_vacancies`'s `stale_days` convention.
    """
    effective_date = date if date is not None else datetime.now().astimezone().date()
    return add_document(
        vacancy_id, DocumentKind.NOTE, text, NOTE_TITLE, effective_date, vault=vault
    )


# --- Writing: set_status() ----------------------------------------------


class InvalidStatusValueError(CoreError):
    """Raised when `set_status`'s `new_status` doesn't parse as a
    `Status` - names every permitted value."""

    def __init__(self, value: object) -> None:
        self.value = value
        permitted = ", ".join(s.value for s in Status)
        super().__init__(
            f"{value!r} is not a valid status; permitted values: {permitted}"
        )


class InvalidStatusTransitionError(CoreError):
    """Raised when a transition isn't in `models.STATUS_TRANSITIONS`
    and `force` wasn't given - names both statuses (design.md decision
    5)."""

    def __init__(self, current: Status, requested: Status) -> None:
        self.current = current
        self.requested = requested
        super().__init__(
            f"cannot move from {current.value!r} to {requested.value!r} without force"
        )


class MissingAppliedDateError(CoreError):
    """Raised when a transition moves a vacancy off `found` and it has
    no `applied_date` yet, and none was given - the model's conditional
    rule (models.py) surfaced as a typed, actionable error (design.md
    decision 7)."""

    def __init__(self, vacancy_id: str, target_status: Status) -> None:
        self.vacancy_id = vacancy_id
        self.target_status = target_status
        super().__init__(
            f"{vacancy_id!r} has no applied_date; moving it to "
            f"{target_status.value!r} requires one"
        )


class InvalidVacancyDataError(CoreError):
    """Raised when writing would produce a `vacancy.md` that fails
    `Vacancy`'s own validation - wraps the underlying
    `pydantic.ValidationError` rather than letting it escape raw."""

    def __init__(self, vacancy_id: str, cause: Exception) -> None:
        self.vacancy_id = vacancy_id
        self.cause = cause
        super().__init__(f"{vacancy_id!r}: invalid vacancy data: {cause}")


@dataclass(frozen=True)
class StatusChange:
    """The outcome of one `set_status` call. `changed=False` marks the
    same-status no-op - `old_status == new_status` in that case, and
    nothing in the vault was written."""

    vacancy_id: str
    old_status: Status
    new_status: Status
    changed: bool
    applied_date: date | None = None


STATUS_HISTORY_HEADING = "## Status History"
"""The status-history block's heading. Always the final section of
`vacancy.md`'s body (design.md decision 6) - `set_status` only ever
appends after it, never parses markdown section boundaries."""


def _resolve_applied_date(
    vacancy_id: str,
    target_status: Status,
    current_applied_date: date | None,
    given_applied_date: date | None,
) -> date | None:
    if target_status is Status.FOUND:
        # The model forbids applied_date when status is found - a
        # forced backward transition to found always clears it.
        return None
    if given_applied_date is not None:
        return given_applied_date
    if current_applied_date is not None:
        return current_applied_date
    raise MissingAppliedDateError(vacancy_id, target_status)


def _append_status_history(
    body: str, old_status: Status, new_status: Status, note: str | None
) -> str:
    today = datetime.now().astimezone().date()
    entry = f"- {today.isoformat()}: {old_status.value} -> {new_status.value}"
    if note:
        entry += f" ({note})"

    if STATUS_HISTORY_HEADING in body:
        return f"{body.rstrip(chr(10))}\n{entry}\n"

    stripped = body.rstrip("\n")
    prefix = f"{stripped}\n\n" if stripped else ""
    return f"{prefix}{STATUS_HISTORY_HEADING}\n{entry}\n"


def set_status(  # noqa: PLR0913 - the deliverable's public signature; each is meaningful
    vacancy_id: str,
    new_status: Status | str,
    note: str | None = None,
    applied_date: date | None = None,
    *,
    force: bool = False,
    vault: Path | None = None,
) -> StatusChange:
    """Validate and apply a status transition, per `models.
    STATUS_TRANSITIONS` (design.md decision 5).

    A same-status call is always a no-op, regardless of `force`. A
    transition not in the permitted graph raises unless `force=True`.
    Moving a vacancy off `found` for the first time requires
    `applied_date` (design.md decision 7) - explicitly, never guessed.
    Writes `vacancy.md`'s frontmatter (`status`, and `applied_date` when
    it changes) and appends to the status-history block, preserving
    every other line byte-for-byte (design.md decision 6) - `stage_note`
    is never touched. Refreshes the index before returning; that
    vacancy's document rows get the new status without being
    re-embedded (design.md decision 4).
    """
    vault_root = resolve_vault_path(vault)
    snapshot = read_vault(vault_root)

    if vacancy_id not in snapshot.vacancies:
        raise EntityNotFoundError(vacancy_id)
    vacancy = snapshot.vacancies[vacancy_id]

    try:
        target_status = Status(new_status)
    except ValueError:
        raise InvalidStatusValueError(new_status) from None

    current_status = vacancy.status
    if target_status == current_status:
        return StatusChange(
            vacancy_id=vacancy_id,
            old_status=current_status,
            new_status=current_status,
            changed=False,
            applied_date=vacancy.applied_date,
        )

    if not force and target_status not in STATUS_TRANSITIONS[current_status]:
        raise InvalidStatusTransitionError(current_status, target_status)

    effective_applied_date = _resolve_applied_date(
        vacancy_id, target_status, vacancy.applied_date, applied_date
    )

    vacancy_path = snapshot.vacancy_paths[vacancy_id]
    _ensure_within_vault(vault_root, vacancy_path)
    original_text = vacancy_path.read_text(encoding="utf-8")
    metadata, body = frontmatter.parse(original_text, filename=str(vacancy_path))

    metadata["status"] = target_status.value
    if effective_applied_date is None:
        metadata.pop("applied_date", None)
    else:
        metadata["applied_date"] = effective_applied_date.isoformat()

    try:
        Vacancy(**metadata)
    except ValidationError as exc:
        raise InvalidVacancyDataError(vacancy_id, exc) from exc

    new_body = _append_status_history(body, current_status, target_status, note)
    new_text = frontmatter.serialize(metadata, new_body)
    _atomic_write(vacancy_path, new_text, overwrite=True)

    reindex(vault=vault_root)

    return StatusChange(
        vacancy_id=vacancy_id,
        old_status=current_status,
        new_status=target_status,
        changed=True,
        applied_date=effective_applied_date,
    )


# --- Writing: create_vacancy() ------------------------------------------


def _existing_ids_for_collision_check(
    snapshot: VaultSnapshot, company_directory: Path
) -> set[str]:
    """Every vacancy id `new_vacancy_id` must not collide with: the
    snapshot's own ids, plus any subdirectory name already present
    under the company's directory - belt-and-suspenders against a
    vacancy directory that failed to parse (and so isn't in
    `snapshot.vacancies`) but would still collide on disk."""
    existing_ids = set(snapshot.vacancies)
    if company_directory.is_dir():
        existing_ids |= {p.name for p in company_directory.iterdir() if p.is_dir()}
    return existing_ids


def create_vacancy(  # noqa: PLR0913, PLR0917 - the deliverable's public signature; each is meaningful
    company: str,
    role: str,
    source_url: str,
    found_date: date,
    status: Status | str,
    applied_date: date | None = None,
    stage_note: str | None = None,
    salary_note: str | None = None,
    recruiter: str | None = None,
    tags: list[str] | None = None,
    *,
    vault: Path | None = None,
) -> Path:
    """Create a new vacancy, minting its id via `ids.new_vacancy_id`
    (colliding against both the vault's known ids and, defensively, any
    raw subdirectory already on disk). Creates the company directory
    and `_company.md` only when the derived slug has neither yet;
    leaves an existing company's `_company.md` untouched (design.md
    decision 8). Never overwrites anything - `new_vacancy_id`'s
    suffixing means a second call with the same inputs mints a distinct
    id, not a collision. `stage_note`/`salary_note`/`recruiter`/`tags`
    are optional and forwarded to `Vacancy` unchanged (`tags` defaults
    to an empty list, matching `Vacancy`'s own default, when omitted) -
    see the llm-import change's design.md decision 5. Refreshes the
    index before returning."""
    vault_root = resolve_vault_path(vault)
    snapshot = read_vault(vault_root)

    company_slug = slugify(company)
    company_directory = company_dir(vault_root, company_slug)
    company_md_path = company_markdown_path(vault_root, company_slug)

    existing_ids = _existing_ids_for_collision_check(snapshot, company_directory)
    vacancy_id = new_vacancy_id(found_date, company_slug, role, existing_ids)

    try:
        target_status = Status(status)
        vacancy = Vacancy(
            id=vacancy_id,
            company=company,
            company_slug=company_slug,
            role=role,
            source_url=source_url,
            status=target_status,
            found_date=found_date,
            applied_date=applied_date,
            stage_note=stage_note,
            salary_note=salary_note,
            recruiter=recruiter,
            tags=tags or [],
        )
    except ValueError as exc:
        # pydantic.ValidationError subclasses ValueError, so this catches
        # both Status(status)'s invalid-value error and Vacancy's own
        # field/model validation in one place.
        raise InvalidVacancyDataError(vacancy_id, exc) from exc

    if not company_md_path.exists():
        _ensure_within_vault(vault_root, company_md_path)
        company_record = Company(slug=company_slug, name=company)
        company_metadata = company_record.model_dump(mode="json", exclude_none=True)
        _atomic_write(
            company_md_path,
            frontmatter.serialize(company_metadata, ""),
            overwrite=False,
        )

    vacancy_md_path = vacancy_markdown_path(vault_root, company_slug, vacancy_id)
    _ensure_within_vault(vault_root, vacancy_md_path)
    vacancy_metadata = vacancy.model_dump(
        mode="json", exclude={"role_is_placeholder"}, exclude_none=True
    )
    vacancy_text = frontmatter.serialize(vacancy_metadata, f"# {vacancy.role}\n")
    _atomic_write(vacancy_md_path, vacancy_text, overwrite=False)

    reindex(vault=vault_root)
    return vacancy_md_path


# --- Writing: find_existing() --------------------------------------------


def find_existing(
    company: str, source_url: str, vault: Path | None = None
) -> list[VacancySummary]:
    """Best-effort pre-check for `create_vacancy` callers: every vacancy
    matching `company` (via `resolve`'s own, non-raising company-tier
    matching) unioned with every vacancy whose `source_url` equals the
    given one exactly, deduplicated. Never raises - an unresolved or
    ambiguous `company` simply contributes no rows from that tier
    (llm-import change's design.md decisions 2-3); a `source_url` match
    still applies even when `company`'s spelling doesn't resolve to
    that vacancy's own company. One `read_vault` call, reusing
    `resolve`'s and `list_vacancies`'s own private helpers rather than
    calling either public function (which would each re-read the
    vault) - see design.md decision 2."""
    snapshot = read_vault(resolve_vault_path(vault))

    matched_ids: dict[str, None] = {}

    resolution = _resolve(company, snapshot)
    if resolution.company_slug is not None:
        for vacancy in snapshot.vacancies.values():
            if vacancy.company_slug == resolution.company_slug:
                matched_ids[vacancy.id] = None

    for vacancy in snapshot.vacancies.values():
        if vacancy.source_url == source_url:
            matched_ids[vacancy.id] = None

    return [_vacancy_summary(vacancy_id, snapshot) for vacancy_id in matched_ids]
