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

Writes take no lock (the lock-free-vault-writes change): they run
concurrently from MCP worker threads, several server processes, and the
CLI. New files are published so they can never replace one another,
`vacancy.md` updates refuse to overwrite a concurrent change, and the
post-write index refresh retries LanceDB commit conflicts and, if they
persist, leaves the index stale rather than failing the write.
"""

import contextlib
import difflib
import logging
import os
import random
import tempfile
import time
from collections.abc import Iterable, Iterator, Mapping
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


logger = logging.getLogger(__name__)


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


class AmbiguousVacancyError(CoreError):
    """Raised when a query resolves to a company holding more than one
    vacancy, so there is no single vacancy to write to - the vacancy-
    level counterpart to `AmbiguousEntityError` (resolve-write-target-
    vacancy's design.md decision 3). Never picks one."""

    def __init__(
        self, query: str, company_slug: str, vacancy_ids: tuple[str, ...]
    ) -> None:
        self.query = query
        self.company_slug = company_slug
        self.vacancy_ids = vacancy_ids
        ids = ", ".join(vacancy_ids)
        super().__init__(
            f"{query!r} matches company {company_slug!r}, which has "
            f"{len(vacancy_ids)} vacancies: {ids}"
        )


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


def resolve_vacancy(query: str, vault: Path | None = None) -> str:
    """Resolve `query` to exactly one vacancy id, for the write commands
    (resolve-write-target-vacancy's design.md).

    Runs `resolve`'s own tiers - exact vacancy id, exact company slug,
    exact company name, unambiguous fuzzy company name - and then
    narrows a company-tier match to that company's single vacancy
    (decision 2). Never guesses: a company holding several vacancies
    raises `AmbiguousVacancyError` naming every candidate id, a company
    holding none raises `EntityNotFoundError`, and an ambiguous company
    query raises `AmbiguousEntityError` before narrowing is reached.

    `resolve` itself is unchanged and still answers a company query with
    a company - which is what `show`, `get_company`, and `find_existing`
    need (decision 5). This is the narrower question the write half
    asks, not a replacement for it.
    """
    snapshot = read_vault(resolve_vault_path(vault))
    resolution = _resolve(query, snapshot)

    if resolution.vacancy_id is not None:
        return resolution.vacancy_id
    if resolution.candidates:
        raise AmbiguousEntityError(query, resolution.candidates)
    if resolution.company_slug is None:
        raise EntityNotFoundError(query)

    vacancy_ids = tuple(
        vacancy_id
        for vacancy_id, vacancy in snapshot.vacancies.items()
        if vacancy.company_slug == resolution.company_slug
    )
    if not vacancy_ids:
        raise EntityNotFoundError(query)
    if len(vacancy_ids) > 1:
        raise AmbiguousVacancyError(query, resolution.company_slug, vacancy_ids)
    return vacancy_ids[0]


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
    resume: str | None = None


def list_vacancies(  # noqa: PLR0913 - the deliverable's public signature; each is meaningful
    *,
    status: list[Status] | None = None,
    company: str | None = None,
    since: date | None = None,
    stale_days: int | None = None,
    needs_review: bool = False,
    resume: str | None = None,
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
    if resume is not None:
        wanted_resume = _resume_key(resume)
        vacancies = [v for v in vacancies if _resume_key(v.resume) == wanted_resume]
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


def _resume_key(resume: str | None) -> str | None:
    """A resume label's comparison form: trimmed and case-folded, so
    `Backend-V2` and ` backend-v2 ` are one variant."""
    if resume is None:
        return None
    return resume.strip().casefold()


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
        resume=vacancy.resume,
    )


# --- Resume comparison -----------------------------------------------------

ADVANCED_STATUSES: frozenset[Status] = frozenset(
    {Status.SCREENING, Status.TAKE_HOME, Status.INTERVIEW, Status.OFFER}
)
"""The statuses `resume_stats` counts as "advanced" - the application
got past the initial applied state and was not (yet) turned down or
dropped. Read from current status only (add-resume-tracking's
design.md decision 5)."""


class ResumeStats(BaseModel):
    """One `resume_stats` row: how the applications sent with one
    resume label currently stand. `resume=None` is the row for
    applications recorded without a resume."""

    resume: str | None
    applications: int
    by_status: dict[Status, int]
    advanced: int
    advance_rate: float | None


def resume_stats(
    since: date | None = None, vault: Path | None = None
) -> list[ResumeStats]:
    """Compare resume variants by how their applications turned out.

    Only vacancies that have been applied to (status other than
    `found`) are counted; `since` keeps those whose `applied_date` is on
    or after it. Labels group case-insensitively after trimming and are
    reported lower-cased. Read from the vault snapshot - the index is
    never opened. Rows run by application count descending, then label,
    with the no-resume row last."""
    snapshot = read_vault(resolve_vault_path(vault))

    grouped: dict[str | None, list[Vacancy]] = {}
    for vacancy in snapshot.vacancies.values():
        if vacancy.status is Status.FOUND or vacancy.applied_date is None:
            continue
        if since is not None and vacancy.applied_date < since:
            continue
        grouped.setdefault(_resume_key(vacancy.resume), []).append(vacancy)

    rows: list[ResumeStats] = []
    for key, vacancies in grouped.items():
        by_status = {
            status: count
            for status in Status
            if (count := sum(1 for v in vacancies if v.status is status))
        }
        advanced = sum(1 for v in vacancies if v.status in ADVANCED_STATUSES)
        rows.append(
            ResumeStats(
                resume=key,
                applications=len(vacancies),
                by_status=by_status,
                advanced=advanced,
                advance_rate=advanced / len(vacancies),
            )
        )

    rows.sort(key=lambda r: (r.resume is None, -r.applications, r.resume or ""))
    return rows


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
    source_url: str | None = None
    found_date: date
    applied_date: date | None = None
    stage_note: str | None = None
    salary_note: str | None = None
    recruiter: str | None = None
    external_id: str | None = None
    resume: str | None = None
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
        resume=vacancy.resume,
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
    without touching `path`. The guard holds against concurrent writers
    too (lock-free-vault-writes design.md decision 1): the temp file is
    published with a hard link, which fails atomically if another
    writer created `path` first, where `exists()` + `os.replace` would
    silently clobber it. `overwrite=True` replaces `path`'s content,
    still atomically.
    """
    if not overwrite and path.exists():
        raise DocumentAlreadyExistsError(path)

    with _temp_file_beside(path, text) as tmp_path:
        if overwrite:
            tmp_path.replace(path)
        else:
            _publish_new(tmp_path, path)


@contextlib.contextmanager
def _temp_file_beside(path: Path, text: str) -> Iterator[Path]:
    """A dot-prefixed temp file holding `text` in `path`'s directory
    (invisible to the vault reader), removed on exit whether or not it
    was published."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=_TEMP_SUFFIX, dir=path.parent
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def _publish_new(tmp_path: Path, path: Path) -> None:
    """Make `tmp_path`'s complete content appear at `path`, failing with
    `DocumentAlreadyExistsError` rather than replacing an existing file."""
    try:
        os.link(tmp_path, path)
    except FileExistsError:
        raise DocumentAlreadyExistsError(path) from None
    except OSError:
        # No hard links on this filesystem (some FUSE, exFAT, network
        # mounts): claim `path` exclusively, then replace the empty
        # claim. A reader may briefly see it empty; never clobbered.
        _publish_new_without_link(tmp_path, path)


def _publish_new_without_link(tmp_path: Path, path: Path) -> None:
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        raise DocumentAlreadyExistsError(path) from None
    try:
        tmp_path.replace(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


class ConcurrentModificationError(CoreError):
    """Raised when a file changed between being read and being
    rewritten - another writer got there first. Nothing was written;
    retrying the call re-reads the new content."""

    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(
            f"{path} was changed by another writer while this update was "
            "being prepared; nothing was written - retry"
        )


def _replace_if_unchanged(path: Path, expected: str, text: str) -> None:
    """Atomically replace `path` with `text`, but only if it still holds
    `expected` (lock-free-vault-writes design.md decision 3). Compares
    bytes, not mtime, whose resolution varies by filesystem. A change
    landing between the re-read and the rename is still lost - a
    two-syscall window, accepted."""
    with _temp_file_beside(path, text) as tmp_path:
        if path.read_text(encoding="utf-8") != expected:
            raise ConcurrentModificationError(path)
        tmp_path.replace(path)


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


def reindex(
    *, force: bool = False, extract_sidecars: bool = False, vault: Path | None = None
) -> IndexReport:
    """Wrap stage 3's incremental `build_index` over a fresh
    `VaultSnapshot` (design.md decision 4). Every write function below
    calls this with `force=False` as its last step, before returning -
    the same call `vacancy-radar reindex` makes directly. Cheap when
    little changed: `build_index` diffs by content hash and re-embeds
    only what's new or changed.

    `extract_sidecars` defaults to `False` and is forwarded to
    `build_index` unchanged - PDF sidecar extraction stays opt-in, per
    stage 3's design.md ("a build must not silently create sidecar
    files on every run"), reachable now via `vacancy-radar reindex
    --extract-sidecars` (see the sidecar-extraction-cli change's
    design.md decision 1).

    Concurrent writers share the index without a lock: a LanceDB commit
    conflict is retried (lock-free-vault-writes design.md decision 4),
    and one that persists raises here. Write functions refresh through
    `_refresh_after_write` instead, which logs rather than raises."""
    vault_root = resolve_vault_path(vault)
    return _reindex_with_retry(
        vault_root, force=force, extract_sidecars=extract_sidecars
    )


_REINDEX_ATTEMPTS = 5
_REINDEX_BACKOFF_SECONDS = 0.05


_LANCE_CONFLICT_MARKERS = (
    "Retryable commit conflict",  # optimize()/FTS create_index lost a race
    "Incompatible transaction",  # e.g. an update racing a first build's overwrite
)


def _is_retryable_conflict(exc: BaseException) -> bool:
    """LanceDB 0.37 reports a transaction that lost to a concurrent
    writer only as a `RuntimeError` with one of these phrases - there's
    no dedicated type to catch. LanceDB itself can't rebase an
    "incompatible" one, but rerunning our whole build from the vault
    files is always safe. `test_is_retryable_conflict_matches_a_real_
    lancedb_conflict` pins the wording against a real conflict."""
    return isinstance(exc, RuntimeError) and any(
        marker in str(exc) for marker in _LANCE_CONFLICT_MARKERS
    )


def _reindex_with_retry(
    vault_root: Path, *, force: bool = False, extract_sidecars: bool = False
) -> IndexReport:
    """Retrying rebuilds the whole index, which stays cheap: rows the
    failed attempt already wrote have matching hashes, so only the FTS
    index and compaction rerun. Each attempt reads a fresh snapshot."""
    index_path = default_index_path(vault_root)
    for attempt in range(_REINDEX_ATTEMPTS):
        try:
            return build_index(
                read_vault(vault_root),
                index_path,
                force=force,
                extract_sidecars=extract_sidecars,
            )
        except RuntimeError as exc:
            if not _is_retryable_conflict(exc) or attempt == _REINDEX_ATTEMPTS - 1:
                raise
            delay = _REINDEX_BACKOFF_SECONDS * 2**attempt
            time.sleep(delay * (1 + random.random()))  # noqa: S311 - jitter, not crypto
    raise AssertionError  # unreachable: the loop returns or raises


def _refresh_after_write(vault_root: Path) -> None:
    """A write's last step. The file change is already durable; if the
    index stays contended after retries, leave it stale (search reports
    staleness, the next reindex converges) rather than fail the write."""
    try:
        _reindex_with_retry(vault_root)
    except RuntimeError as exc:
        if not _is_retryable_conflict(exc):
            raise
        logger.warning(
            "index refresh for %s lost to concurrent writers; the index is "
            "stale until the next reindex: %s",
            vault_root,
            exc,
        )


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
    # A concurrent writer can take the derived name between derivation
    # and publish; re-deriving then yields the next free suffix.
    for _ in range(_MAX_FILENAME_SUFFIX_ATTEMPTS):
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
        try:
            _atomic_write(target, text, overwrite=False)
            break
        except DocumentAlreadyExistsError:
            continue
    else:
        raise DocumentAlreadyExistsError(target)

    _refresh_after_write(vault_root)
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
"""The status-history block's heading (design.md decision 6)."""

EDIT_HISTORY_HEADING = "## Edit History"
"""The edit-history block's heading - `edit_vacancy`'s counterpart to
`STATUS_HISTORY_HEADING` (edit-vacancy-fields' design.md decision 5).
The two blocks are independent: each append lands inside its own
section, whichever order they appear in."""

_SECTION_BOUNDARY_PREFIX = "## "


def _append_to_section(body: str, heading: str, entries: Iterable[str]) -> str:
    """Append `entries` as the last lines of `heading`'s own section.

    A section runs from its heading to the next `##` heading or the end
    of the body, so an append lands inside the right block even when
    another one follows it (edit-vacancy-fields' design.md decision 6) -
    what the previous end-of-body append could not guarantee once
    `vacancy.md` could carry two history blocks. When `heading` is
    absent, the section is created at the end of the body; when it is
    the body's last section, the output is byte-identical to that
    earlier append.
    """
    new_lines = list(entries)
    if not new_lines:
        return body

    lines = body.split("\n")
    heading_index = next(
        (index for index, line in enumerate(lines) if line.strip() == heading), None
    )
    if heading_index is None:
        stripped = body.rstrip("\n")
        prefix = f"{stripped}\n\n" if stripped else ""
        return prefix + heading + "\n" + "".join(f"{line}\n" for line in new_lines)

    end = len(lines)
    for index in range(heading_index + 1, len(lines)):
        if lines[index].startswith(_SECTION_BOUNDARY_PREFIX):
            end = index
            break

    # Trailing blank lines belong to the gap before the next section (or
    # to the end of the file), not to this section's entries.
    insert_at = end
    while insert_at > heading_index + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1

    appended_at_end = insert_at == len(lines)
    result = "\n".join(lines[:insert_at] + new_lines + lines[insert_at:])
    if appended_at_end and not result.endswith("\n"):
        # Matches the trailing newline the prior end-of-body append
        # always left behind.
        result += "\n"
    return result


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
    return _append_to_section(body, STATUS_HISTORY_HEADING, [entry])


def set_status(  # noqa: PLR0913 - the deliverable's public signature; each is meaningful
    vacancy_id: str,
    new_status: Status | str,
    note: str | None = None,
    applied_date: date | None = None,
    *,
    resume: str | None = None,
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
    re-embedded (design.md decision 4). Raises
    `ConcurrentModificationError`, writing nothing, if `vacancy.md`
    changed after it was read.

    `resume`, when given, records the resume variant used in the same
    write; a value that differs from the stored one also lands in the
    `## Edit History` block (add-resume-tracking's design.md decision 4).
    A same-status call ignores it - use `edit_vacancy`.
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

    if resume is not None:
        metadata["resume"] = resume

    try:
        updated = Vacancy(**metadata)
    except ValidationError as exc:
        raise InvalidVacancyDataError(vacancy_id, exc) from exc

    new_body = _append_status_history(body, current_status, target_status, note)
    if resume is not None:
        # The validated (trimmed) value, so the file never stores the
        # untrimmed form.
        metadata["resume"] = updated.resume
        if updated.resume != vacancy.resume:
            new_body = _append_edit_history(
                new_body,
                [FieldChange(field="resume", old=vacancy.resume, new=updated.resume)],
            )
    new_text = frontmatter.serialize(metadata, new_body)
    _replace_if_unchanged(vacancy_path, original_text, new_text)

    _refresh_after_write(vault_root)

    return StatusChange(
        vacancy_id=vacancy_id,
        old_status=current_status,
        new_status=target_status,
        changed=True,
        applied_date=effective_applied_date,
    )


# --- Writing: edit_vacancy() --------------------------------------------


class _UnsetType:
    """The type of `UNSET` - a distinct singleton, never a value a
    caller could mean."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _UnsetType()
"""Every `edit_vacancy` field parameter's default: "leave this field
alone". `None` cannot serve that purpose - most editable fields are
nullable, so `None` is a real value meaning "clear it" (edit-vacancy-
fields' design.md decision 2)."""

type Unsettable[T] = T | _UnsetType

EDITABLE_FIELDS: tuple[str, ...] = (
    "source_url",
    "role",
    "stage_note",
    "salary_note",
    "recruiter",
    "external_id",
    "tags",
    "found_date",
    "applied_date",
    "resume",
)
"""Exactly the fields `edit_vacancy` accepts. `id`, `status`,
`company`, and `company_slug` are absent by design (edit-vacancy-fields'
design.md decision 3): the id is immutable and names the vacancy's
directory, `status` belongs to `set_status` and its transition graph,
and the company pair determines where the vacancy directory lives."""

NULLABLE_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {"source_url", "stage_note", "salary_note", "recruiter", "external_id",
     "applied_date", "resume"}
)  # fmt: skip
"""The editable fields that can be cleared. `role` and `found_date` are
mandatory on `Vacancy`; `tags` is emptied by setting `[]`, not cleared."""


class UneditableFieldError(CoreError):
    """Raised when a caller names a field that `edit_vacancy` does not
    accept - only reachable from the CLI and MCP surfaces, which pass
    field names as strings (design.md decision 9)."""

    def __init__(self, field: str) -> None:
        self.field = field
        editable = ", ".join(EDITABLE_FIELDS)
        super().__init__(f"{field!r} is not an editable field; editable: {editable}")


class NotNullableFieldError(CoreError):
    """Raised when a caller asks to clear a field that must always have
    a value."""

    def __init__(self, field: str) -> None:
        self.field = field
        nullable = ", ".join(sorted(NULLABLE_EDITABLE_FIELDS))
        super().__init__(f"{field!r} cannot be cleared; clearable fields: {nullable}")


class ConflictingEditError(CoreError):
    """Raised when one field is both given a value and named for
    clearing in the same call."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"{field!r} cannot be both set and cleared in one edit")


@dataclass(frozen=True)
class FieldChange:
    """One field an `edit_vacancy` call actually changed, with the
    parsed values on either side of it."""

    field: str
    old: object
    new: object


@dataclass(frozen=True)
class EditResult:
    """The outcome of one `edit_vacancy` call. `changed=False` marks the
    no-op - `changes` is empty in that case, and nothing in the vault
    was written."""

    vacancy_id: str
    changed: bool
    changes: tuple[FieldChange, ...] = ()

    @property
    def changed_fields(self) -> tuple[str, ...]:
        return tuple(change.field for change in self.changes)


def resolve_field_edits(
    values: Mapping[str, object | None], clear: Iterable[str] | None = None
) -> dict[str, object | None]:
    """Map a string-keyed set of field values and clear requests onto
    `edit_vacancy` keyword arguments, for the CLI and MCP surfaces,
    which cannot pass `UNSET` (design.md decision 9).

    In `values`, `None` means "not given" - those keys are dropped; a
    field is cleared by naming it in `clear` instead, which maps it to
    `None` in the result. Field names accept hyphens (`salary-note`),
    the form a CLI option carries. Raises `UneditableFieldError`,
    `NotNullableFieldError`, and `ConflictingEditError` - the only
    runtime field-name checks in the design.
    """
    resolved: dict[str, object | None] = {}
    for name, value in values.items():
        if value is None:
            continue
        field = _normalize_field_name(name)
        resolved[field] = value

    for name in clear or ():
        field = _normalize_field_name(name)
        if field not in NULLABLE_EDITABLE_FIELDS:
            raise NotNullableFieldError(field)
        if field in resolved:
            raise ConflictingEditError(field)
        resolved[field] = None

    return resolved


def _normalize_field_name(name: str) -> str:
    field = name.strip().lower().replace("-", "_")
    if field not in EDITABLE_FIELDS:
        raise UneditableFieldError(field)
    return field


_MAX_HISTORY_VALUE_LENGTH = 120
"""How much of a value an edit-history entry carries before it is
truncated - the entry is a pointer to what changed, not a backup of the
value (design.md's risks)."""


def render_history_value(value: object) -> str:
    """Render one side of an edit-history entry as a single line - also
    what the CLI prints for a changed field, so the two agree.

    Multi-line values are collapsed to their first line plus a count,
    so no value - a `stage_note` pasted from an email, say - can
    introduce what reads as an additional history entry.
    """
    if value is None or value == []:
        return "(none)"
    if isinstance(value, date):
        text = value.isoformat()
    elif isinstance(value, list | tuple):
        text = ", ".join(str(item) for item in value)
    else:
        text = str(value)

    lines = text.splitlines() or [""]
    head = lines[0]
    if len(head) > _MAX_HISTORY_VALUE_LENGTH:
        head = head[: _MAX_HISTORY_VALUE_LENGTH - 3].rstrip() + "..."
    if len(lines) > 1:
        head += f" [+{len(lines) - 1} more lines]"
    return head or "(empty)"


def _append_edit_history(body: str, changes: Iterable[FieldChange]) -> str:
    today = datetime.now().astimezone().date()
    entries = [
        f"- {today.isoformat()}: {change.field}: "
        f"{render_history_value(change.old)} -> {render_history_value(change.new)}"
        for change in changes
    ]
    return _append_to_section(body, EDIT_HISTORY_HEADING, entries)


def _apply_field_to_metadata(
    metadata: dict[str, object], field: str, value: object
) -> None:
    """Set or remove one frontmatter key, writing dates in the ISO form
    every other writer in this module uses."""
    if value is None:
        metadata.pop(field, None)
    elif isinstance(value, date):
        metadata[field] = value.isoformat()
    elif isinstance(value, list | tuple):
        metadata[field] = list(value)
    else:
        metadata[field] = value


def edit_vacancy(  # noqa: PLR0913 - the deliverable's public signature; one parameter per editable field
    vacancy_id: str,
    *,
    source_url: Unsettable[str | None] = UNSET,
    role: Unsettable[str] = UNSET,
    stage_note: Unsettable[str | None] = UNSET,
    salary_note: Unsettable[str | None] = UNSET,
    recruiter: Unsettable[str | None] = UNSET,
    external_id: Unsettable[str | None] = UNSET,
    tags: Unsettable[list[str]] = UNSET,
    found_date: Unsettable[date] = UNSET,
    applied_date: Unsettable[date | None] = UNSET,
    resume: Unsettable[str | None] = UNSET,
    vault: Path | None = None,
) -> EditResult:
    """Set one or more of a vacancy's editable frontmatter fields in a
    single validated, atomic write (edit-vacancy-fields' design.md).

    Every field parameter defaults to `UNSET` ("leave it alone"); a
    nullable field passed as `None` is cleared. `status`, `id`,
    `company`, and `company_slug` are not parameters - the signature is
    what makes them uneditable, so passing one is a `TypeError` at the
    call site rather than a runtime rejection (decision 1).

    The merged frontmatter is validated by constructing a whole
    `Vacancy` before anything is written, so cross-field rules apply
    even to fields the caller did not give (decision 4) - clearing
    `applied_date` on a vacancy that has moved off `found` raises
    `InvalidVacancyDataError`, and the file is left untouched. A call
    that changes nothing writes nothing, appends no history, and does
    not reindex (decision 7). Every applied change appends an entry to
    the `## Edit History` block; every other line of `vacancy.md`,
    including the body's `# {role}` heading, is preserved byte-for-byte
    (decisions 5 and 8). The vacancy's id and directory never change,
    even when `found_date` or `role` - which contributed to that id
    when it was minted - are edited (decision 3). Raises
    `ConcurrentModificationError`, writing nothing, if `vacancy.md`
    changed after it was read.
    """
    vault_root = resolve_vault_path(vault)
    snapshot = read_vault(vault_root)

    if vacancy_id not in snapshot.vacancies:
        raise EntityNotFoundError(vacancy_id)
    vacancy = snapshot.vacancies[vacancy_id]

    given: dict[str, object] = {
        field: value
        for field, value in (
            ("source_url", source_url),
            ("role", role),
            ("stage_note", stage_note),
            ("salary_note", salary_note),
            ("recruiter", recruiter),
            ("external_id", external_id),
            ("tags", tags),
            ("found_date", found_date),
            ("applied_date", applied_date),
            ("resume", resume),
        )
        if not isinstance(value, _UnsetType)
    }
    if not given:
        return EditResult(vacancy_id=vacancy_id, changed=False)

    vacancy_path = snapshot.vacancy_paths[vacancy_id]
    _ensure_within_vault(vault_root, vacancy_path)
    original_text = vacancy_path.read_text(encoding="utf-8")
    metadata, body = frontmatter.parse(original_text, filename=str(vacancy_path))

    for field, value in given.items():
        _apply_field_to_metadata(metadata, field, value)

    try:
        updated = Vacancy(**metadata)
    except ValidationError as exc:
        raise InvalidVacancyDataError(vacancy_id, exc) from exc

    # Compared on the parsed models, not on raw YAML, so an edit that
    # restates a stored value - `tags=[]` against an absent `tags`, an
    # unchanged date written differently - is the no-op it looks like.
    changes = tuple(
        FieldChange(
            field=field, old=getattr(vacancy, field), new=getattr(updated, field)
        )
        for field in given
        if getattr(vacancy, field) != getattr(updated, field)
    )
    if not changes:
        return EditResult(vacancy_id=vacancy_id, changed=False)

    # Re-derived from the untouched original so that only the keys that
    # actually changed are rewritten: a field given a value it already
    # holds keeps its own quoting style, byte for byte.
    metadata, body = frontmatter.parse(original_text, filename=str(vacancy_path))
    for change in changes:
        _apply_field_to_metadata(metadata, change.field, change.new)

    new_body = _append_edit_history(body, changes)
    _replace_if_unchanged(
        vacancy_path, original_text, frontmatter.serialize(metadata, new_body)
    )

    _refresh_after_write(vault_root)

    return EditResult(vacancy_id=vacancy_id, changed=True, changes=changes)


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
    found_date: date,
    status: Status | str,
    source_url: str | None = None,
    applied_date: date | None = None,
    stage_note: str | None = None,
    salary_note: str | None = None,
    recruiter: str | None = None,
    tags: list[str] | None = None,
    resume: str | None = None,
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
    id, not a collision. `source_url`/`stage_note`/`salary_note`/
    `recruiter`/`tags`/`resume` are optional and forwarded to `Vacancy` unchanged
    (`tags` defaults to an empty list, matching `Vacancy`'s own default,
    when omitted) - see the llm-import change's design.md decision 5
    and the optional-vacancy-url change's design.md decision 1 (the
    signature reorder that moved `source_url` here, since `found_date`/
    `status` after it must stay required). Refreshes the index before
    returning. Callers SHOULD use keyword arguments - positional calls
    written against the pre-reorder argument order will silently
    misassign values rather than raise a clean error."""
    vault_root = resolve_vault_path(vault)
    snapshot = read_vault(vault_root)

    company_slug = slugify(company)
    company_directory = company_dir(vault_root, company_slug)
    company_md_path = company_markdown_path(vault_root, company_slug)

    existing_ids = _existing_ids_for_collision_check(snapshot, company_directory)
    fields: dict[str, object] = {
        "company": company,
        "company_slug": company_slug,
        "role": role,
        "source_url": source_url,
        "status": status,
        "found_date": found_date,
        "applied_date": applied_date,
        "stage_note": stage_note,
        "salary_note": salary_note,
        "recruiter": recruiter,
        "tags": tags or [],
        "resume": resume,
    }
    # Validate before touching the vault, so invalid input writes nothing.
    vacancy = _new_vacancy_record(
        new_vacancy_id(found_date, company_slug, role, existing_ids), fields
    )

    if not company_md_path.exists():
        _ensure_within_vault(vault_root, company_md_path)
        company_record = Company(slug=company_slug, name=company)
        company_metadata = company_record.model_dump(mode="json", exclude_none=True)
        # A concurrent create for the same new company may win this
        # race; its `_company.md` describes the same slug, so keep it.
        with contextlib.suppress(DocumentAlreadyExistsError):
            _atomic_write(
                company_md_path,
                frontmatter.serialize(company_metadata, ""),
                overwrite=False,
            )

    # A concurrent create can publish the minted id first; mint the next.
    for _ in range(_MAX_FILENAME_SUFFIX_ATTEMPTS):
        vacancy_md_path = vacancy_markdown_path(vault_root, company_slug, vacancy.id)
        _ensure_within_vault(vault_root, vacancy_md_path)
        vacancy_metadata = vacancy.model_dump(
            mode="json", exclude={"role_is_placeholder"}, exclude_none=True
        )
        vacancy_text = frontmatter.serialize(vacancy_metadata, f"# {vacancy.role}\n")
        try:
            _atomic_write(vacancy_md_path, vacancy_text, overwrite=False)
            break
        except DocumentAlreadyExistsError:
            existing_ids.add(vacancy.id)
            vacancy = _new_vacancy_record(
                new_vacancy_id(found_date, company_slug, role, existing_ids), fields
            )
    else:
        raise DocumentAlreadyExistsError(vacancy_md_path)

    _refresh_after_write(vault_root)
    return vacancy_md_path


def _new_vacancy_record(vacancy_id: str, fields: Mapping[str, object]) -> Vacancy:
    try:
        return Vacancy.model_validate({"id": vacancy_id, **fields})
    except ValueError as exc:
        # pydantic.ValidationError subclasses ValueError, so this catches
        # both Status(status)'s invalid-value error and Vacancy's own
        # field/model validation in one place.
        raise InvalidVacancyDataError(vacancy_id, exc) from exc


# --- Writing: find_existing() --------------------------------------------


def find_existing(
    company: str, source_url: str | None = None, vault: Path | None = None
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
    vault) - see design.md decision 2.

    `source_url` is optional - a caller may have none to check against
    (e.g. a recruiter sent only a PDF, no posting link). The source_url
    tier only ever contributes a match when `source_url` is not `None`
    and equals a vacancy's own non-`None` `source_url` exactly - two
    vacancies that both lack a `source_url` are never matched to each
    other on that basis (optional-vacancy-url change's design.md
    decision 2)."""
    snapshot = read_vault(resolve_vault_path(vault))

    matched_ids: dict[str, None] = {}

    resolution = _resolve(company, snapshot)
    if resolution.company_slug is not None:
        for vacancy in snapshot.vacancies.values():
            if vacancy.company_slug == resolution.company_slug:
                matched_ids[vacancy.id] = None

    if source_url is not None:
        for vacancy in snapshot.vacancies.values():
            if vacancy.source_url == source_url:
                matched_ids[vacancy.id] = None

    return [_vacancy_summary(vacancy_id, snapshot) for vacancy_id in matched_ids]
