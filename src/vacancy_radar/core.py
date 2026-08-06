"""Read-only business-logic entry points shared by the CLI (this stage)
and, later, the MCP server (stage 8) - see design.md decision 1
(invariant 4: every read a caller needs lives here exactly once, never
duplicated inside a CLI command or an MCP tool).

Every function resolves its own vault (an explicit `vault` argument, or
`VAULT_PATH`, via `config.resolve_vault_path` - the same precedence
`search()` and `doctor()` use) and reads it fresh via
`vault.reader.read_vault`. Nothing here writes to the vault or the
index; writes are stage 7.
"""

import difflib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from vacancy_radar.config import resolve_vault_path
from vacancy_radar.index import search as index_search
from vacancy_radar.index.build import TABLE_NAME
from vacancy_radar.index.embed import DEFAULT_EMBEDDING_MODEL_NAME, vector_dim
from vacancy_radar.index.store import IndexHandle, default_index_path, get_index_handle
from vacancy_radar.models import DocumentKind, Status
from vacancy_radar.vault.paths import is_within
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
