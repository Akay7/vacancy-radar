"""MCP server exposing `core.py` as tools, resources, and prompts.

Invariant 4 (`core.py`'s own module docstring: "shared by the CLI and,
later, the MCP server (stage 8)"): every tool here is argument
marshalling around exactly one `core.py` call, never new business
logic. If a tool needs behavior `core.py` doesn't provide, that's a
`core.py` change proposed separately - never inline here. The MCP Apps
`ui://` views are not an exception: they are static `.html`/`.css`/`.js`
files under `assets/mcp_ui/`, concatenated once at import and served
verbatim, and a client that does not negotiate the extension gets the
tool's ordinary text result unchanged.

Invariant 5: nothing is written to stdout except JSON-RPC frames.
Diagnostics (startup failures, warnings) go to stderr - `sys.stderr`
directly for the one pre-transport failure mode (`main`'s vault-path
resolution), the SDK's own `logging` configuration (stderr by default)
for everything after the server starts. No `print()` call exists
anywhere in this module (T20).

Vault-path resolution: `--vault` > `VAULT_PATH`, via
`config.resolve_vault_path` unchanged - see design.md decision 7. MCP
roots (a client-supplied workspace-folder capability) are deliberately
not used: the installed MCP Python SDK's default protocol revision
(2026-07-28, SEP-2577) deprecates the entire roots capability, and the
high-level `FastMCP` class this module builds on exposes no
supported hook for `notifications/roots/list_changed` at all. The
resolved vault path is fixed for the life of the process and closed
over by every tool/resource/prompt function `build_server` registers -
see design.md decision 8. Every `core.py` call still passes that path
as its own `vault=` argument, so index-handle resolution goes through
`index.store.get_index_handle`'s existing per-path cache unchanged;
this module never resolves or caches an `IndexHandle` of its own.
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import inspect
import sys
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import (
    UI_MIME_TYPE,
    AppConfig,
    ResourceCSP,
    app_config_to_meta_dict,
)
from fastmcp.exceptions import ToolError
from fastmcp.resources import TextResource
from mcp.types import ToolAnnotations
from pydantic import BaseModel

import vacancy_radar
from vacancy_radar import core
from vacancy_radar.config import (
    VaultNotConfiguredError,
    VaultNotFoundError,
    resolve_vault_path,
)
from vacancy_radar.index.search import SearchError, SearchMode
from vacancy_radar.models import STATUS_TRANSITIONS, DocumentKind, Status
from vacancy_radar.vault.reader import read_vault

_TYPED_ERRORS: tuple[type[Exception], ...] = (
    VaultNotConfiguredError,
    VaultNotFoundError,
    core.CoreError,
    SearchError,
)
"""Every typed error a tool's one `core.py`/`config.py`/`index.search`
call can raise - mirrors `cli.py`'s own `_CORE_ERRORS` tuple, caught
uniformly at the same boundary a CLI command is."""

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
_WRITE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, open_world_hint=False
)
"""Fixed annotation objects, applied verbatim to every read/write tool
(spec `mcp-read-tools`/`mcp-write-tools`) - never computed per tool."""


# --- MCP Apps: the `ui://` views ---------------------------------------
#
# Presentation only, and static: the views are plain .html/.css/.js files
# under `assets/mcp_ui/`, assembled once at import into whole documents and
# served verbatim. Nothing here reads the vault or reshapes a result, so
# Invariant 4 holds - the server ships an asset, it does not render one.
# A client that does not negotiate the Apps extension never asks for these
# and sees exactly the text it always has.

VIEW_URIS: dict[str, str] = {
    "list_vacancies": "ui://vacancy-radar/vacancy-list",
    "get_vacancy": "ui://vacancy-radar/vacancy-detail",
    "get_company": "ui://vacancy-radar/company-dossier",
    "search": "ui://vacancy-radar/search-results",
}
"""Tool name -> `ui://` view URI. Exactly the read tools that get a
`_meta.ui` reference; every other tool gets none."""

_VIEW_TITLES: dict[str, str] = {
    "list_vacancies": "Vacancies",
    "get_vacancy": "Vacancy",
    "get_company": "Company",
    "search": "Search results",
}

_ASSETS = resources.files(vacancy_radar) / "assets" / "mcp_ui"


def _asset(name: str) -> str:
    """One view asset's text, read from the installed package."""
    return (_ASSETS / name).read_text(encoding="utf-8")


RENDER_JS: dict[str, str] = {
    tool: _asset(f"{uri.rsplit('/', 1)[-1]}.js") for tool, uri in VIEW_URIS.items()
}
"""Tool name -> its view's render-function source, exposed so a test can
check which result fields a view reads without parsing the whole page."""


def _build_pages() -> dict[str, tuple[str, str]]:
    """`ui://` URI -> `(title, html)` for every view: the shared shell,
    stylesheet, DOM helpers, and host bridge, plus the view's own render
    function. A pure concatenation of static fragments - no vault data
    reaches it."""
    shell, css = _asset("page.html"), _asset("view.css")
    helpers, bridge = _asset("helpers.js"), _asset("bridge.js")
    return {
        uri: (
            _VIEW_TITLES[tool],
            shell.replace("__TITLE__", _VIEW_TITLES[tool])
            .replace("__STYLE__", css)
            .replace("__SCRIPT__", "\n".join((helpers, RENDER_JS[tool], bridge))),
        )
        for tool, uri in VIEW_URIS.items()
    }


PAGES: dict[str, tuple[str, str]] = _build_pages()
"""Every view document, assembled once at import."""


def _ui_app(tool_name: str) -> AppConfig:
    """The `AppConfig` binding `tool_name` to the `ui://` view a
    UI-capable host renders for it (spec `mcp-apps-ui`); FastMCP
    stamps it as `_meta.ui.resourceUri`. The tool's own result is
    unchanged; a client that did not negotiate the Apps extension
    ignores this. Only the four tools in `VIEW_URIS` get one."""
    return AppConfig(resource_uri=VIEW_URIS[tool_name])


# --- Shared helpers: serialization and typed-error wrapping ----------------

type JSONValue = (
    bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None
)
"""What `_to_jsonable` guarantees its result is - precise enough that
neither its parameter nor its return type needs `Any` (ANN401): the
parameter is `object`, narrowed by each `isinstance` check below, and
every branch either returns a `JSONValue` leaf directly or reduces to
one of the two recursive cases (`list`/`dict`) that do."""


def _to_jsonable(value: object) -> JSONValue:
    """Convert a `core.py` return value into a JSON-safe structure,
    without reshaping its fields (design.md decision 2): a
    `pydantic.BaseModel` via its own `model_dump(mode="json")`, a
    `dataclasses.dataclass` via its own fields, a `Path` or `date` via
    its string/ISO form, recursing through lists/tuples/dicts. Every
    tool's result passes through this unchanged apart from the type
    conversion itself.

    A `BaseModel`/dataclass is reduced to its own dict of raw field
    values and falls through to the `dict` branch below, rather than
    recursing explicitly - the same recursive conversion either way,
    with one fewer branch (keeps this under `PLR0911`'s return-count
    limit honestly, not by suppressing it).
    """
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    elif is_dataclass(value) and not isinstance(value, type):
        value = {f.name: getattr(value, f.name) for f in fields(value)}

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value  # type: ignore[return-value] - already a JSONValue leaf (str/int/float/bool/None)


def _delegate[F: Callable[..., Any]](fn: F) -> F:
    """Wrap one tool handler: run it, convert its result via
    `_to_jsonable`, and turn any typed `core.py`/`config.py`/
    `index.search` error into a `ToolError` naming the error's own type
    (design.md decision 9) - FastMCP's own tool-call handling already
    converts a `ToolError` into a tool result with `isError=true`,
    never a JSON-RPC protocol error, so nothing here constructs a
    `CallToolResult` directly. Applied to
    every tool function; no tool duplicates this try/except itself.

    Tool bodies are plain sync functions calling blocking `core.py`
    code (file IO, reindex, embedding-model load); they run via
    `asyncio.to_thread` so they never stall the event loop - blocking
    it made the server unresponsive and clients time out after every
    write/reindex. Coroutine functions are still awaited directly."""

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        try:
            if inspect.iscoroutinefunction(fn):
                result = await fn(*args, **kwargs)
            else:
                result = await asyncio.to_thread(fn, *args, **kwargs)
        except _TYPED_ERRORS as exc:
            message = f"{type(exc).__name__}: {exc}"
            raise ToolError(message) from exc
        return _to_jsonable(result)

    return wrapper  # type: ignore[return-value]


# --- Server construction -----------------------------------------------


_LOCKED_CSP = ResourceCSP(connect_domains=[], resource_domains=[], frame_domains=[])
"""A Content-Security-Policy permitting no external domain at all -
applied to every `ui://` view (spec `mcp-apps-ui`)."""


def _register_views(server: FastMCP) -> None:
    """Register every `ui://` view from `PAGES` as a self-contained
    HTML resource under the MCP Apps mime type, with a
    Content-Security-Policy that permits no external domain (spec
    `mcp-apps-ui`). FastMCP advertises `io.modelcontextprotocol/ui`
    for these; a client that did not negotiate it never asks for them
    and falls back to the tool's own text result.
    """
    for uri, (title, html) in PAGES.items():
        server.add_resource(
            TextResource(
                uri=uri,
                name=uri,
                title=title,
                mime_type=UI_MIME_TYPE,
                meta={"ui": app_config_to_meta_dict(AppConfig(csp=_LOCKED_CSP))},
                text=html,
            )
        )


def build_server(vault_path: Path) -> FastMCP:
    """Build the MCP server for `vault_path`, fixed for the life of the
    returned server (design.md decisions 7-8). Every tool, resource,
    and prompt function defined here closes over `vault_path` and
    passes it straight through as the one `core.py` call's `vault=`
    argument - no tool resolves or caches its own vault path or index
    handle.
    """
    server: FastMCP = FastMCP(
        name="vacancy-radar",
        version=vacancy_radar.__version__,
        instructions=(
            "Tools for a local-first job application vault: read vacancies, "
            "companies, and documents; search the vault; append notes, "
            "change status, correct a vacancy's stored fields, file "
            "documents, and create new vacancies "
            "(e.g. when importing an existing tracker conversationally - "
            "see create_vacancy's own description). Reindexing is "
            "intentionally not exposed here - use `vacancy-radar reindex` "
            "if that's ever needed; every write tool already refreshes "
            "the index itself."
        ),
    )

    _register_views(server)
    _register_read_tools(server, vault_path)
    _register_write_tools(server, vault_path)
    _register_resources(server, vault_path)
    _register_prompts(server, vault_path)

    return server


# --- Read tools ----------------------------------------------------------


def _register_read_tools(server: FastMCP, vault_path: Path) -> None:
    @server.tool(annotations=_READ_ONLY, app=_ui_app("list_vacancies"))
    @_delegate
    def list_vacancies(  # noqa: PLR0913, PLR0917 - mirrors core.list_vacancies's own signature
        status: list[Status] | None = None,
        company: str | None = None,
        since: date | None = None,
        stale_days: int | None = None,
        needs_review: bool = False,  # noqa: FBT001, FBT002 - mirrors core.list_vacancies's own signature
        limit: int = core.DEFAULT_LIST_LIMIT,
    ) -> list[core.VacancySummary]:
        """List vacancies, optionally filtered by status, company,
        applied-on-or-after date, staleness (days since last activity),
        or the needs_review tag. Returns compact summaries - id,
        company, role, status, dates, document count - never document
        bodies. Bounded by limit (default 50)."""
        return core.list_vacancies(
            status=status,
            company=company,
            since=since,
            stale_days=stale_days,
            needs_review=needs_review,
            limit=limit,
            vault=vault_path,
        )

    @server.tool(annotations=_READ_ONLY, app=_ui_app("get_company"))
    @_delegate
    def get_company(name: str) -> core.CompanyDossier:
        """Get one company's dossier: display name, domains,
        recruiters, notes (from _company.md when present), and every
        vacancy at that company as a compact summary with document
        counts and paths - never document bodies. `name` may be a
        company slug or a fuzzy display-name match; an ambiguous or
        unresolved name returns a typed error rather than guessing."""
        return core.get_company(name, vault=vault_path)

    @server.tool(annotations=_READ_ONLY, app=_ui_app("get_vacancy"))
    @_delegate
    def get_vacancy(id_or_query: str) -> core.VacancyDetail:
        """Get one vacancy's full record: role, status, dates,
        recruiter, stage_note, tags, and its documents as a list of
        paths and titles - never document bodies. Use read_document to
        read a specific document's content. `id_or_query` may be an
        exact vacancy id or a fuzzy match."""
        return core.get_vacancy(id_or_query, vault=vault_path)

    @server.tool(annotations=_READ_ONLY, app=_ui_app("search"))
    @_delegate
    def search(  # noqa: PLR0913, PLR0917 - mirrors core.search's own signature
        query: str,
        mode: SearchMode | None = None,
        company: str | None = None,
        status: list[Status] | None = None,
        kind: list[DocumentKind] | None = None,
        limit: int | None = None,
    ) -> core.SearchResults:
        """Search the vault's index. Returns snippets and paths, never
        full document bodies - call read_document for a specific hit's
        full text.

        Prefer mode="keyword" for an exact company name, job title, or
        other proper-noun lookup: a 30-query sweep across this vault
        found keyword search ahead of hybrid specifically on exact-name
        queries. Leave mode unset (hybrid, the configured default) for
        conceptual or paraphrased queries, where hybrid measured the
        best overall recall (0.794 vs. keyword's 0.761 recall@5) - see
        README.md's retrieval evaluation table. Do not default to
        hybrid for every query; the mode choice is deliberate.
        """
        return core.search(
            query,
            vault=vault_path,
            mode=mode,
            company_slug=company,
            status=status,
            kind=kind,
            limit=limit,
        )

    @server.tool(annotations=_READ_ONLY)
    @_delegate
    def read_document(path: str) -> core.DocumentContent:
        """Read one vault document's full text by path (absolute or
        vault-relative, as returned by list_vacancies/get_vacancy/
        get_company/search). Rejects any path resolving outside the
        vault."""
        return core.read_document(path, vault=vault_path)

    @server.tool(annotations=_READ_ONLY)
    @_delegate
    def resolve(query: str) -> core.Resolution:
        """Resolve a query to a vacancy id or a company slug: exact
        vacancy id, then exact company slug, then a unique company-name
        match (case-insensitive, then fuzzy). Never guesses - an
        ambiguous query returns every candidate instead of picking
        one."""
        return core.resolve(query, vault=vault_path)

    @server.tool(annotations=_READ_ONLY)
    @_delegate
    def find_existing(
        company: str, source_url: str | None = None
    ) -> list[core.VacancySummary]:
        """Check for a vacancy that might already exist before calling
        create_vacancy. Returns every vacancy under a company matching
        company (by the same rules resolve uses), unioned with every
        vacancy whose source_url matches exactly - so it still finds a
        match even when company's spelling differs from what's already
        in the vault. source_url may be omitted when there's none to
        check against (e.g. a recruiter sent only a PDF) - matching
        then relies on company alone. Returns an empty list, never an
        error, when nothing matches or company is ambiguous/
        unresolved."""
        return core.find_existing(company, source_url, vault=vault_path)


# --- Write tools -----------------------------------------------------------


def _register_write_tools(server: FastMCP, vault_path: Path) -> None:
    @server.tool(annotations=_WRITE)
    @_delegate
    def append_note(vacancy_id: str, text: str, date: date | None = None) -> str:
        """Append a dated note to a vacancy's documents. date defaults
        to today. Never overwrites an existing note - a second note the
        same day gets its own file."""
        return str(core.append_note(vacancy_id, text, date=date, vault=vault_path))

    @server.tool(annotations=_WRITE)
    @_delegate
    def set_status(
        vacancy_id: str,
        new_status: Status,
        note: str | None = None,
        applied_date: date | None = None,
        force: bool = False,  # noqa: FBT001, FBT002 - mirrors core.set_status's own signature
    ) -> core.StatusChange:
        """Change a vacancy's status, validating the transition against
        the permitted status graph (see the vacancy-radar://statuses
        resource). Moving a vacancy off "found" for the first time
        requires applied_date. A backward transition requires
        force=true. Appends a dated entry to the vacancy's status
        history; never touches stage_note."""
        return core.set_status(
            vacancy_id,
            new_status,
            note=note,
            applied_date=applied_date,
            force=force,
            vault=vault_path,
        )

    @server.tool(annotations=_WRITE)
    @_delegate
    def edit_vacancy(  # noqa: PLR0913, PLR0917 - mirrors core.edit_vacancy's own signature
        vacancy_id: str,
        source_url: str | None = None,
        role: str | None = None,
        stage_note: str | None = None,
        salary_note: str | None = None,
        recruiter: str | None = None,
        external_id: str | None = None,
        tags: list[str] | None = None,
        found_date: date | None = None,
        applied_date: date | None = None,
        clear: list[str] | None = None,
    ) -> core.EditResult:
        """Correct a vacancy's stored fields - a moved posting URL, a
        role that was "unknown" when it was captured, a mistyped date.

        Omitting a parameter leaves that field alone; there is no way to
        set a field to null by passing null. To remove a field, name it
        in clear (e.g. clear=["recruiter"]) - only source_url,
        stage_note, salary_note, recruiter, external_id, and
        applied_date can be cleared. tags replaces the whole list, so
        pass the tags you want to keep alongside any you are adding.

        Status is not editable here - use set_status, which validates
        the transition. A vacancy's company and id cannot be changed at
        all. Every applied change is recorded in the vacancy's edit
        history; a call that would change nothing writes nothing."""
        edits = core.resolve_field_edits(
            {
                "source_url": source_url,
                "role": role,
                "stage_note": stage_note,
                "salary_note": salary_note,
                "recruiter": recruiter,
                "external_id": external_id,
                "tags": tags,
                "found_date": found_date,
                "applied_date": applied_date,
            },
            clear,
        )
        return core.edit_vacancy(vacancy_id, vault=vault_path, **edits)

    @server.tool(annotations=_WRITE)
    @_delegate
    def add_document(  # noqa: PLR0913, PLR0917 - mirrors core.add_document's own signature
        vacancy_id: str,
        kind: DocumentKind,
        content: str,
        title: str,
        date: date,
        external_id: str | None = None,
    ) -> str:
        """File a document (posting, email, note, or take-home) under a
        vacancy. The filename is always derived from date/kind/title -
        there is no way to choose a filename or write path directly, so
        this is safe to call with content and titles taken verbatim
        from an untrusted source such as a forwarded recruiter email.
        Passing external_id makes re-filing the same source (e.g. the
        same email thread) a no-op instead of a duplicate."""
        return str(
            core.add_document(
                vacancy_id, kind, content, title, date, external_id, vault=vault_path
            )
        )

    @server.tool(annotations=_WRITE)
    @_delegate
    def create_vacancy(  # noqa: PLR0913, PLR0917 - mirrors core.create_vacancy's own signature
        company: str,
        role: str,
        found_date: date,
        status: Status,
        source_url: str | None = None,
        applied_date: date | None = None,
        stage_note: str | None = None,
        salary_note: str | None = None,
        recruiter: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, str]:
        """Create a new vacancy, and its company directory if one
        doesn't exist yet. This tool exists for conversational import:
        the caller (you) is responsible for mapping a source record's
        fields onto this schema before calling it.

        Use role="unknown" when no job title is available in the
        source, and tag such vacancies "needs_review" so a human can
        revisit them later. found_date may be synthesized from
        applied_date when the source has no found date recorded (e.g.
        an old tracker that only logged when you applied); tag such
        records "migrated" so they're identifiable afterwards.
        source_url may be omitted entirely when the source has no link
        at all - e.g. a recruiter who emailed only a PDF attachment,
        no posting URL.

        This tool does not deduplicate: call find_existing with the
        same company and source_url first (or just company, when
        there's no source_url to check against), and only call this
        tool if it returns no match - two calls with the same inputs
        create two distinct vacancies, not one."""
        path = core.create_vacancy(
            company,
            role,
            found_date,
            status,
            source_url=source_url,
            applied_date=applied_date,
            stage_note=stage_note,
            salary_note=salary_note,
            recruiter=recruiter,
            tags=tags,
            vault=vault_path,
        )
        return {"path": str(path), "id": path.parent.name}


# --- Resources ---------------------------------------------------------


def _register_resources(server: FastMCP, vault_path: Path) -> None:
    @server.resource(
        "vacancy-radar://companies",
        name="companies",
        description=(
            "Every company in the vault: slug, display name, and vacancy "
            "count. Read this once to resolve a company by name without a "
            "tool round-trip."
        ),
    )
    def companies() -> list[dict[str, object]]:
        snapshot = read_vault(vault_path)
        registry: dict[str, str] = {c.slug: c.name for c in snapshot.companies.values()}
        for vacancy in snapshot.vacancies.values():
            registry.setdefault(vacancy.company_slug, vacancy.company)

        counts: dict[str, int] = {}
        for vacancy in snapshot.vacancies.values():
            counts[vacancy.company_slug] = counts.get(vacancy.company_slug, 0) + 1

        return [
            {"slug": slug, "name": name, "vacancy_count": counts.get(slug, 0)}
            for slug, name in sorted(registry.items())
        ]

    @server.resource(
        "vacancy-radar://statuses",
        name="statuses",
        description=(
            "Every vacancy status and the statuses reachable from it "
            "without force, read live from models.py."
        ),
    )
    def statuses() -> list[dict[str, object]]:
        return [
            {
                "status": status.value,
                "transitions": sorted(s.value for s in STATUS_TRANSITIONS[status]),
            }
            for status in Status
        ]


# --- Prompts -------------------------------------------------------------

_DOSSIER_DOCUMENT_KINDS = (
    DocumentKind.POSTING,
    DocumentKind.NOTE,
    DocumentKind.TAKEHOME,
)
_REPLY_DOCUMENT_KINDS = (DocumentKind.EMAIL, DocumentKind.NOTE)
_WEEKLY_STALE_DAYS = 14


def _candidates_text(candidates: tuple[core.ResolutionCandidate, ...]) -> str:
    return ", ".join(f"{c.name} ({c.slug})" for c in candidates)


def _resolution_failure_text(
    query: str, resolution: core.Resolution, *, noun: str
) -> str:
    """The shared not-found/ambiguous message `prep_interview` and
    `draft_reply` both return in place of a dossier/thread they cannot
    honestly compose - never a fabrication (design.md decision 11)."""
    if resolution.candidates:
        return (
            f"{query!r} is ambiguous - candidates: "
            f"{_candidates_text(resolution.candidates)}. Ask which {noun} is "
            "meant rather than guessing."
        )
    return (
        f"No {noun} in the vault matches {query!r}. Do not fabricate one - "
        "ask the user to check it."
    )


def _document_bodies(
    detail: core.VacancyDetail, kinds: tuple[DocumentKind, ...], vault_path: Path
) -> list[str]:
    sections = []
    for doc in detail.documents:
        if doc.kind not in kinds:
            continue
        content = core.read_document(doc.path, vault=vault_path)
        sections.append(
            f"## {doc.kind.value}: {doc.title} ({doc.date})\n\n{content.text}"
        )
    return sections


def _prep_interview_text(vault_path: Path, company: str) -> str:
    resolution = core.resolve(company, vault=vault_path)
    if resolution.company_slug is None:
        return _resolution_failure_text(company, resolution, noun="company")

    dossier = core.get_company(resolution.company_slug, vault=vault_path)
    sections = [f"# Interview prep: {dossier.name} ({dossier.slug})"]
    if dossier.notes:
        sections.append(f"Notes: {dossier.notes}")
    for summary in dossier.vacancies:
        detail = core.get_vacancy(summary.id, vault=vault_path)
        sections.append(
            f"## Vacancy: {detail.role} ({detail.id}, {detail.status.value})"
        )
        sections.extend(_document_bodies(detail, _DOSSIER_DOCUMENT_KINDS, vault_path))
    return "\n\n".join(sections)


def _draft_reply_text(vault_path: Path, vacancy_id: str) -> str:
    resolution = core.resolve(vacancy_id, vault=vault_path)
    if resolution.vacancy_id is None:
        return _resolution_failure_text(vacancy_id, resolution, noun="vacancy")

    detail = core.get_vacancy(resolution.vacancy_id, vault=vault_path)
    sections = [f"# Draft reply: {detail.role} at {detail.company} ({detail.id})"]
    bodies = _document_bodies(detail, _REPLY_DOCUMENT_KINDS, vault_path)
    sections.extend(
        bodies or ["No prior emails or notes are filed for this vacancy yet."]
    )
    return "\n\n".join(sections)


def _weekly_review_rows(summaries: list[core.VacancySummary]) -> list[str]:
    return [f"- {s.company}: {s.role} ({s.id}, {s.status.value})" for s in summaries]


def _weekly_review_text(vault_path: Path) -> str:
    stale = core.list_vacancies(stale_days=_WEEKLY_STALE_DAYS, vault=vault_path)
    take_home = core.list_vacancies(status=[Status.TAKE_HOME], vault=vault_path)
    needs_review = core.list_vacancies(needs_review=True, vault=vault_path)

    sections = [
        "# Weekly review",
        "## Stale applications\n" + "\n".join(_weekly_review_rows(stale) or ["(none)"]),
        "## Pending take-homes\n"
        + "\n".join(_weekly_review_rows(take_home) or ["(none)"]),
        "## Needs review\n"
        + "\n".join(_weekly_review_rows(needs_review) or ["(none)"]),
    ]
    return "\n\n".join(sections)


def _register_prompts(server: FastMCP, vault_path: Path) -> None:
    @server.prompt()
    def prep_interview(company: str) -> str:
        """Interview prep dossier for a company: its vacancies,
        postings, prior notes, and take-home documents."""
        return _prep_interview_text(vault_path, company)

    @server.prompt()
    def draft_reply(vacancy_id: str) -> str:
        """Prior correspondence and notes for a vacancy, to draft a
        reply in a consistent tone."""
        return _draft_reply_text(vault_path, vacancy_id)

    @server.prompt()
    def weekly_review() -> str:
        """Stale applications, pending take-homes, and vacancies
        tagged needs_review."""
        return _weekly_review_text(vault_path)


# --- Entry point ---------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vacancy-radar-mcp")
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Path to the vault. Overrides VAULT_PATH.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point for `vacancy-radar-mcp`. Resolves the vault path
    (--vault > VAULT_PATH; design.md decision 7), building and running
    the stdio server. A vault-path failure is reported on stderr and
    exits non-zero before any server construction - never written to
    stdout, and never a partially-started server."""
    args = _parse_args(argv)

    try:
        vault_path = resolve_vault_path(args.vault)
    except VaultNotConfiguredError as exc:
        # config.py's own message already names VAULT_PATH; add one line
        # naming --vault explicitly (`config.py` has no CLI-flag concept
        # of its own to name) rather than duplicating precedence logic
        # here - the message still names both mechanisms, per spec
        # `mcp-vault-path`.
        sys.stderr.write(f"vacancy-radar-mcp: {exc}\n")
        sys.stderr.write("vacancy-radar-mcp: pass --vault or set VAULT_PATH.\n")
        raise SystemExit(1) from exc
    except VaultNotFoundError as exc:
        sys.stderr.write(f"vacancy-radar-mcp: {exc}\n")
        raise SystemExit(1) from exc

    server = build_server(vault_path)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
