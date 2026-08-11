import dataclasses
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table

import vacancy_radar
from vacancy_radar import core
from vacancy_radar.config import VaultNotConfiguredError, VaultNotFoundError
from vacancy_radar.index.build import build_index
from vacancy_radar.index.search import SearchError, SearchMode
from vacancy_radar.index.store import default_index_path, get_index_handle
from vacancy_radar.models import DocumentKind, Status
from vacancy_radar.vault.reader import read_vault

app = typer.Typer()
console = Console()
error_console = Console(stderr=True)

_CORE_ERRORS = (
    VaultNotConfiguredError,
    VaultNotFoundError,
    core.CoreError,
    SearchError,
)
"""Every typed error a `core.py` call can raise, caught uniformly at the
CLI boundary and rendered as an error message plus a non-zero exit -
this is rendering, not business logic (design.md decision 1)."""


def _version_callback(*, value: bool) -> None:
    if value:
        typer.echo(vacancy_radar.__version__)
        raise typer.Exit(code=0)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    *,
    version: bool = typer.Option(  # noqa: ARG001
        default=False,
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """vacancy-radar: local-first job application tracker."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)


# --- Shared CLI helpers: argument parsing, error/JSON rendering ------------


def _fail(exc: Exception) -> NoReturn:
    error_console.print(f"Error: {exc}")
    raise typer.Exit(code=1)


def _parse_date_option(value: str | None, *, option: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        error_console.print(
            f"Error: {option} must be an ISO date (YYYY-MM-DD), got {value!r}"
        )
        raise typer.Exit(code=1) from None


def _parse_statuses(values: list[str] | None) -> list[Status] | None:
    if not values:
        return None
    try:
        return [Status(v) for v in values]
    except ValueError as exc:
        error_console.print(f"Error: invalid --status value: {exc}")
        raise typer.Exit(code=1) from None


def _parse_mode(value: str | None) -> SearchMode | None:
    if value is None:
        return None
    try:
        return SearchMode(value)
    except ValueError as exc:
        error_console.print(f"Error: invalid --mode value: {exc}")
        raise typer.Exit(code=1) from None


def _json_default(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _print_json(payload: object) -> None:
    text = json.dumps(payload, indent=2, default=_json_default)
    console.print(text, markup=False, highlight=False, soft_wrap=True)


def _parse_kind(value: str) -> DocumentKind:
    try:
        return DocumentKind(value)
    except ValueError as exc:
        error_console.print(f"Error: invalid --kind value: {exc}")
        raise typer.Exit(code=1) from None


def _resolve_vacancy_or_fail(query: str) -> str:
    """Every write command that takes a vacancy argument resolves it
    this way: `core.resolve_vacancy`, which applies `resolve`'s tiers
    and then narrows a company-tier match to that company's single
    vacancy (resolve-write-target-vacancy's design.md decision 4). This
    function holds no resolution rule of its own - only the rendering
    of what came back. An ambiguous or unresolved query prints and
    exits non-zero *before* any write command goes on to call a
    `core.py` write function."""
    try:
        return core.resolve_vacancy(query)
    except core.AmbiguousEntityError as exc:
        _render_candidates(query, exc.candidates)
        raise typer.Exit(code=1) from None
    except _CORE_ERRORS as exc:
        _fail(exc)


def _render_write_outcome(
    path: Path, *, outcome: str, as_json: bool, extra: dict[str, object] | None = None
) -> None:
    if as_json:
        payload: dict[str, object] = {"outcome": outcome, "path": str(path)}
        if extra:
            payload.update(extra)
        _print_json(payload)
    else:
        console.print(f"{outcome}: {path}")


# --- list --------------------------------------------------------------


@app.command("list")
def list_command(  # noqa: PLR0913 - each option mirrors list_vacancies's own signature
    status: Annotated[
        list[str] | None,
        typer.Option("--status", help="Filter by status (repeatable)."),
    ] = None,
    company: Annotated[
        str | None, typer.Option("--company", help="Filter by company slug or name.")
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Only vacancies applied on/after this ISO date."),
    ] = None,
    stale_days: Annotated[
        int | None,
        typer.Option("--stale-days", help="Only vacancies stale this many days."),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", help="Maximum rows to return.")
    ] = core.DEFAULT_LIST_LIMIT,
    *,
    needs_review: Annotated[
        bool, typer.Option("--needs-review", help="Only vacancies tagged needs_review.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of a table.")
    ] = False,
) -> None:
    """List vacancies, optionally filtered."""
    try:
        summaries = core.list_vacancies(
            status=_parse_statuses(status),
            company=company,
            since=_parse_date_option(since, option="--since"),
            stale_days=stale_days,
            needs_review=needs_review,
            limit=limit,
        )
    except _CORE_ERRORS as exc:
        _fail(exc)

    if as_json:
        _print_json([s.model_dump(mode="json") for s in summaries])
        return

    _render_vacancy_table(summaries)


def _render_vacancy_table(summaries: list[core.VacancySummary]) -> None:
    table = Table()
    table.add_column("id")
    table.add_column("company")
    table.add_column("role")
    table.add_column("status")
    table.add_column("applied_date")
    table.add_column("last_activity")
    table.add_column("documents", justify="right")
    for s in summaries:
        table.add_row(
            s.id,
            s.company,
            s.role,
            s.status.value,
            s.applied_date.isoformat() if s.applied_date else "-",
            s.last_activity.isoformat(),
            str(s.document_count),
        )
    console.print(table)


# --- show ----------------------------------------------------------------


@app.command("show")
def show_command(
    query: Annotated[str, typer.Argument(help="A vacancy id, or a company name/slug.")],
    *,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of Rich output.")
    ] = False,
) -> None:
    """Show a vacancy or a company, auto-detected via resolve."""
    try:
        resolution = core.resolve(query)
    except _CORE_ERRORS as exc:
        _fail(exc)

    if resolution.vacancy_id is not None:
        _show_vacancy(resolution.vacancy_id, as_json=as_json)
    elif resolution.company_slug is not None:
        _show_company(resolution.company_slug, as_json=as_json)
    elif resolution.candidates:
        _show_candidates(query, resolution.candidates, as_json=as_json)
    else:
        error_console.print(f"Error: nothing in the vault matches {query!r}")
        raise typer.Exit(code=1)


def _show_vacancy(vacancy_id: str, *, as_json: bool) -> None:
    try:
        detail = core.get_vacancy(vacancy_id)
    except _CORE_ERRORS as exc:
        _fail(exc)
    if as_json:
        _print_json({"kind": "vacancy", **detail.model_dump(mode="json")})
    else:
        _render_vacancy_detail(detail)


def _show_company(company_slug: str, *, as_json: bool) -> None:
    try:
        dossier = core.get_company(company_slug)
    except _CORE_ERRORS as exc:
        _fail(exc)
    if as_json:
        _print_json({"kind": "company", **dossier.model_dump(mode="json")})
    else:
        _render_company_dossier(dossier)


def _show_candidates(
    query: str, candidates: "tuple[core.ResolutionCandidate, ...]", *, as_json: bool
) -> None:
    if as_json:
        _print_json(
            {
                "kind": "ambiguous",
                "candidates": [{"slug": c.slug, "name": c.name} for c in candidates],
            }
        )
    else:
        _render_candidates(query, candidates)
    raise typer.Exit(code=1)


def _render_vacancy_detail(detail: core.VacancyDetail) -> None:
    console.print(f"[bold]{detail.role}[/bold] at {detail.company} ({detail.id})")
    console.print(f"status: {detail.status.value}")
    console.print(f"found: {detail.found_date.isoformat()}")
    if detail.applied_date:
        console.print(f"applied: {detail.applied_date.isoformat()}")
    if detail.stage_note:
        console.print(f"stage note: {detail.stage_note}")
    if detail.salary_note:
        console.print(f"salary note: {detail.salary_note}")
    if detail.recruiter:
        console.print(f"recruiter: {detail.recruiter}")
    if detail.tags:
        console.print(f"tags: {', '.join(detail.tags)}")

    table = Table(title="documents")
    table.add_column("date")
    table.add_column("kind")
    table.add_column("title")
    table.add_column("path")
    for d in detail.documents:
        table.add_row(d.date.isoformat(), d.kind.value, d.title, d.path)
    console.print(table)


def _render_company_dossier(dossier: core.CompanyDossier) -> None:
    console.print(f"[bold]{dossier.name}[/bold] ({dossier.slug})")
    if dossier.domains:
        console.print(f"domains: {', '.join(dossier.domains)}")
    if dossier.recruiters:
        console.print(f"recruiters: {', '.join(dossier.recruiters)}")
    if dossier.notes:
        console.print(f"notes: {dossier.notes}")
    for warning in dossier.warnings:
        console.print(f"[yellow]warning:[/yellow] {warning}")
    _render_vacancy_table(dossier.vacancies)


def _render_candidates(
    query: str, candidates: "tuple[core.ResolutionCandidate, ...]"
) -> None:
    error_console.print(f"Error: {query!r} is ambiguous - candidates:")
    for c in candidates:
        error_console.print(f"  {c.name} ({c.slug})")


# --- search ----------------------------------------------------------------


@app.command("search")
def search_command(  # noqa: PLR0913 - each option mirrors core.search's own signature
    query: Annotated[str, typer.Argument(help="The search query.")],
    mode: Annotated[
        str | None, typer.Option("--mode", help="keyword, semantic, or hybrid.")
    ] = None,
    company: Annotated[
        str | None, typer.Option("--company", help="Restrict to this company slug.")
    ] = None,
    status: Annotated[
        list[str] | None,
        typer.Option("--status", help="Restrict to these statuses (repeatable)."),
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Maximum hits to return.")
    ] = None,
    *,
    scores: Annotated[
        bool, typer.Option("--scores", help="Print per-mode ranks and the fused score.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of a table.")
    ] = False,
) -> None:
    """Search the vault's index."""
    try:
        results = core.search(
            query,
            mode=_parse_mode(mode),
            company_slug=company,
            status=_parse_statuses(status),
            limit=limit,
        )
    except _CORE_ERRORS as exc:
        _fail(exc)

    if as_json:
        _print_json(_search_results_json(results))
        return

    _render_search_hits(results, scores=scores)


def _search_results_json(results: core.SearchResults) -> dict[str, object]:
    return {
        "mode": results.mode.value,
        "elapsed_ms": results.elapsed_ms,
        "total_candidates": results.total_candidates,
        "effective_vector_weight": results.effective_vector_weight,
        "warnings": (
            [results.freshness_warning.message] if results.freshness_warning else []
        ),
        "hits": [dataclasses.asdict(h) for h in results.hits],
    }


def _render_search_hits(results: core.SearchResults, *, scores: bool) -> None:
    if results.freshness_warning:
        console.print(f"[yellow]warning:[/yellow] {results.freshness_warning.message}")

    table = Table()
    table.add_column("company")
    table.add_column("role")
    table.add_column("kind")
    table.add_column("date")
    table.add_column("score", justify="right")
    if scores:
        table.add_column("keyword_rank", justify="right")
        table.add_column("semantic_rank", justify="right")
    table.add_column("snippet")

    for hit in results.hits:
        row = [
            hit.company,
            hit.role,
            hit.kind,
            hit.date.isoformat(),
            f"{hit.score:.3f}",
        ]
        if scores:
            row.append(str(hit.keyword_rank) if hit.keyword_rank is not None else "-")
            row.append(str(hit.semantic_rank) if hit.semantic_rank is not None else "-")
        row.append(hit.snippet)
        table.add_row(*row)
    console.print(table)


# --- doctor ----------------------------------------------------------------


@app.command("doctor")
def doctor_command(
    *,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of Rich output.")
    ] = False,
) -> None:
    """Report vault and index health."""
    try:
        report = core.doctor()
    except _CORE_ERRORS as exc:
        _fail(exc)

    if as_json:
        _print_json(report.model_dump(mode="json"))
    else:
        _render_doctor_report(report)

    if not report.healthy:
        raise typer.Exit(code=1)


def _render_doctor_report(report: core.DoctorReport) -> None:
    console.print(f"vault: {report.vault_path}")
    console.print(f"index present: {report.index_present}")
    console.print(f"index fresh: {report.index_fresh}")
    if report.freshness_message:
        console.print(f"[yellow]warning:[/yellow] {report.freshness_message}")
    console.print(f"embedding model available: {report.embedding_model_available}")
    if report.embedding_model_error:
        console.print(
            f"[red]embedding model error:[/red] {report.embedding_model_error}"
        )
    for warning in report.vault_warnings:
        console.print(f"[red]warning:[/red] {warning}")


# --- eval --------------------------------------------------------------


@app.command("eval")
def eval_command() -> None:
    """Run the retrieval eval full sweep against the fixture vault and
    print the resulting report.

    Imports `eval/` from the repo checkout (never shipped in the built
    wheel), so this only works from a plain checkout, not an installed
    package.
    """
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from eval.run import FULL_SWEEP, load_queries, run_eval  # noqa: PLC0415

    queries = load_queries(repo_root / "eval" / "queries.yaml")
    fixture_vault = repo_root / "tests" / "fixtures" / "vault"

    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_root = Path(tmp_dir)
        index_path = default_index_path(vault_root)
        build_index(read_vault(fixture_vault), index_path)
        index = get_index_handle(vault_root)
        report = run_eval(queries, index, FULL_SWEEP)

    typer.echo(report.to_markdown())


# --- note ----------------------------------------------------------------


@app.command("note")
def note_command(
    vacancy: Annotated[
        str, typer.Argument(help="A vacancy id, company name, or fuzzy match.")
    ],
    text: Annotated[str, typer.Argument(help="The note text.")],
    *,
    date: Annotated[
        str | None,
        typer.Option("--date", help="ISO date for the note; defaults to today."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """Append a dated note to a vacancy."""
    vacancy_id = _resolve_vacancy_or_fail(vacancy)
    note_date = _parse_date_option(date, option="--date")

    try:
        path = core.append_note(vacancy_id, text, date=note_date)
    except _CORE_ERRORS as exc:
        _fail(exc)

    _render_write_outcome(path, outcome="created", as_json=as_json)


# --- status ----------------------------------------------------------------

status_app = typer.Typer()
app.add_typer(status_app, name="status", help="Inspect or change a vacancy's status.")


@status_app.command("set")
def status_set_command(  # noqa: PLR0913 - each option mirrors set_status's own signature
    vacancy: Annotated[
        str, typer.Argument(help="A vacancy id, company name, or fuzzy match.")
    ],
    status: Annotated[str, typer.Argument(help="The target status.")],
    note: Annotated[
        str | None,
        typer.Option("--note", help="Recorded alongside the status-history entry."),
    ] = None,
    applied_date: Annotated[
        str | None,
        typer.Option(
            "--applied-date",
            help="Required the first time a vacancy moves off 'found'.",
        ),
    ] = None,
    *,
    force: Annotated[
        bool, typer.Option("--force", help="Allow a backward transition.")
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """Set a vacancy's status, validating the transition."""
    vacancy_id = _resolve_vacancy_or_fail(vacancy)
    applied_date_value = _parse_date_option(applied_date, option="--applied-date")

    try:
        change = core.set_status(
            vacancy_id,
            status,
            note=note,
            applied_date=applied_date_value,
            force=force,
        )
    except _CORE_ERRORS as exc:
        _fail(exc)

    if as_json:
        _print_json(
            {
                "outcome": "changed" if change.changed else "unchanged",
                "vacancy_id": change.vacancy_id,
                "old_status": change.old_status.value,
                "new_status": change.new_status.value,
            }
        )
    elif change.changed:
        console.print(
            f"{change.vacancy_id}: "
            f"{change.old_status.value} -> {change.new_status.value}"
        )
    else:
        console.print(f"{change.vacancy_id}: unchanged ({change.new_status.value})")


# --- edit --------------------------------------------------------------


def _parse_tags_option(value: str | None) -> list[str] | None:
    """`--tags` replaces the whole list (edit-vacancy-fields' design.md
    decision 9): a comma-separated value becomes that exact list, and an
    empty value becomes the empty list - which is why an empty string
    must not read as "option not given"."""
    if value is None:
        return None
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def _render_edit_outcome(result: core.EditResult, *, as_json: bool) -> None:
    if as_json:
        _print_json(
            {
                "outcome": "changed" if result.changed else "unchanged",
                "vacancy_id": result.vacancy_id,
                "changed_fields": list(result.changed_fields),
                "changes": [
                    {"field": c.field, "old": c.old, "new": c.new}
                    for c in result.changes
                ],
            }
        )
        return

    if not result.changed:
        console.print(f"{result.vacancy_id}: unchanged")
        return

    console.print(f"{result.vacancy_id}: {len(result.changes)} field(s) changed")
    for change in result.changes:
        old = core.render_history_value(change.old)
        new = core.render_history_value(change.new)
        console.print(f"  {change.field}: {old} -> {new}")


@app.command("edit")
def edit_command(  # noqa: PLR0913, PLR0917 - one option per editable field, mirroring core.edit_vacancy
    vacancy: Annotated[
        str, typer.Argument(help="A vacancy id, company name, or fuzzy match.")
    ],
    source_url: Annotated[
        str | None, typer.Option("--source-url", help="The posting's URL.")
    ] = None,
    role: Annotated[str | None, typer.Option("--role", help="The job title.")] = None,
    stage_note: Annotated[
        str | None, typer.Option("--stage-note", help="Free-text stage note.")
    ] = None,
    salary_note: Annotated[
        str | None, typer.Option("--salary-note", help="Free-text salary note.")
    ] = None,
    recruiter: Annotated[
        str | None, typer.Option("--recruiter", help="The recruiter's name.")
    ] = None,
    external_id: Annotated[
        str | None, typer.Option("--external-id", help="An external tracker's id.")
    ] = None,
    tags: Annotated[
        str | None,
        typer.Option("--tags", help="Comma-separated; replaces the whole tag list."),
    ] = None,
    found_date: Annotated[
        str | None, typer.Option("--found-date", help="ISO date the vacancy was found.")
    ] = None,
    applied_date: Annotated[
        str | None, typer.Option("--applied-date", help="ISO date you applied.")
    ] = None,
    clear: Annotated[
        list[str] | None,
        typer.Option("--clear", help="Remove a field; repeatable."),
    ] = None,
    *,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """Edit a vacancy's fields, validating the result.

    Status is not editable here - use 'status set', which validates the
    transition. Company is not editable at all.
    """
    vacancy_id = _resolve_vacancy_or_fail(vacancy)
    values: dict[str, object | None] = {
        "source_url": source_url,
        "role": role,
        "stage_note": stage_note,
        "salary_note": salary_note,
        "recruiter": recruiter,
        "external_id": external_id,
        "tags": _parse_tags_option(tags),
        "found_date": _parse_date_option(found_date, option="--found-date"),
        "applied_date": _parse_date_option(applied_date, option="--applied-date"),
    }

    try:
        edits = core.resolve_field_edits(values, clear)
        result = core.edit_vacancy(vacancy_id, vault=None, **edits)
    except _CORE_ERRORS as exc:
        _fail(exc)

    _render_edit_outcome(result, as_json=as_json)


# --- add ---------------------------------------------------------------


_NOT_UTF8_HINT = (
    "add only accepts text content. To attach a binary file such as a "
    "PDF, copy it directly into the vacancy's documents/ directory and "
    "run 'vacancy-radar reindex --extract-sidecars' (PDFs only)."
)


def _read_document_content(*, file: Path | None, stdin: bool) -> str:
    if file is not None and stdin:
        error_console.print("Error: pass either --file or --stdin, not both")
        raise typer.Exit(code=1)
    if file is not None:
        try:
            return file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            error_console.print(
                f"Error: {file} is not valid UTF-8 text - {_NOT_UTF8_HINT}"
            )
            raise typer.Exit(code=1) from None
    if stdin:
        try:
            return sys.stdin.read()
        except UnicodeDecodeError:
            error_console.print(
                f"Error: standard input is not valid UTF-8 text - {_NOT_UTF8_HINT}"
            )
            raise typer.Exit(code=1) from None
    error_console.print("Error: pass either --file or --stdin")
    raise typer.Exit(code=1)


def _document_count(vacancy_id: str) -> int:
    try:
        return len(core.get_vacancy(vacancy_id).documents)
    except _CORE_ERRORS as exc:
        _fail(exc)


@app.command("add")
def add_command(  # noqa: PLR0913 - each option mirrors add_document's own signature
    vacancy: Annotated[
        str, typer.Argument(help="A vacancy id, company name, or fuzzy match.")
    ],
    *,
    kind: Annotated[
        str, typer.Option("--kind", help="posting, email, note, or takehome.")
    ],
    title: Annotated[str, typer.Option("--title", help="The document's title.")],
    date: Annotated[str, typer.Option("--date", help="ISO date for the document.")],
    file: Annotated[
        Path | None,
        typer.Option(
            "--file", help="Read content from this file.", exists=True, readable=True
        ),
    ] = None,
    stdin: Annotated[
        bool, typer.Option("--stdin", help="Read content from standard input.")
    ] = False,
    external_id: Annotated[
        str | None,
        typer.Option(
            "--external-id", help="Dedupe key; re-filing the same id is a no-op."
        ),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """File a document under a vacancy. Content comes from --file or --stdin."""
    vacancy_id = _resolve_vacancy_or_fail(vacancy)
    kind_enum = _parse_kind(kind)
    date_value = _parse_date_option(date, option="--date")
    content = _read_document_content(file=file, stdin=stdin)

    before_count = _document_count(vacancy_id)
    try:
        path = core.add_document(
            vacancy_id, kind_enum, content, title, date_value, external_id
        )
    except _CORE_ERRORS as exc:
        _fail(exc)
    after_count = _document_count(vacancy_id)

    outcome = "created" if after_count > before_count else "existing"
    _render_write_outcome(path, outcome=outcome, as_json=as_json)


# --- init ----------------------------------------------------------------


@app.command("init")
def init_command(
    path: Annotated[
        str | None,
        typer.Argument(
            help="Where to create the vault. Defaults to VAULT_PATH when omitted."
        ),
    ] = None,
    *,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """Create a vault at PATH (or VAULT_PATH). Idempotent - running this
    again against an already-initialized vault changes nothing and
    still exits 0."""
    try:
        result = core.init_vault(path)
    except _CORE_ERRORS as exc:
        _fail(exc)

    outcome = "created" if result.created else "already initialized"
    _render_write_outcome(result.path, outcome=outcome, as_json=as_json)


# --- new ---------------------------------------------------------------


@app.command("new")
def new_command(  # noqa: PLR0913 - each option mirrors create_vacancy's own signature
    *,
    company: Annotated[
        str, typer.Option("--company", help="The company's display name.")
    ],
    role: Annotated[str, typer.Option("--role", help="The role title.")],
    found_date: Annotated[
        str, typer.Option("--found-date", help="ISO date the vacancy was found.")
    ],
    status: Annotated[
        str, typer.Option("--status", help="Initial status; defaults to 'found'.")
    ] = Status.FOUND.value,
    url: Annotated[
        str | None,
        typer.Option(
            "--url", help="The posting's source URL. Omit when the source has none."
        ),
    ] = None,
    applied_date: Annotated[
        str | None,
        typer.Option("--applied-date", help="Required when --status is not 'found'."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """Create a new vacancy, and its company directory if needed."""
    found_date_value = _parse_date_option(found_date, option="--found-date")
    applied_date_value = _parse_date_option(applied_date, option="--applied-date")

    try:
        path = core.create_vacancy(
            company,
            role,
            found_date_value,
            status,
            source_url=url,
            applied_date=applied_date_value,
        )
    except _CORE_ERRORS as exc:
        _fail(exc)

    # The vacancy directory is named after its id (vault/paths.py's own
    # convention, followed by create_vacancy) - reading it back off the
    # returned path is a structural fact, not business logic.
    vacancy_id = path.parent.name
    _render_write_outcome(
        path, outcome="created", as_json=as_json, extra={"id": vacancy_id}
    )


# --- reindex -----------------------------------------------------------


@app.command("reindex")
def reindex_command(
    *,
    force: Annotated[
        bool, typer.Option("--force", help="Re-embed every row, not only changed ones.")
    ] = False,
    extract_sidecars: Annotated[
        bool,
        typer.Option(
            "--extract-sidecars",
            help="Extract text sidecars for eligible PDFs under documents/.",
        ),
    ] = False,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit JSON instead of plain output.")
    ] = False,
) -> None:
    """Rebuild the index from the vault's current state."""
    try:
        report = core.reindex(force=force, extract_sidecars=extract_sidecars)
    except _CORE_ERRORS as exc:
        _fail(exc)

    if as_json:
        _print_json(dataclasses.asdict(report))
    else:
        console.print(
            f"added={report.added} changed={report.changed} deleted={report.deleted} "
            f"unchanged={report.unchanged} skipped={report.skipped}"
        )
        for warning in report.warnings:
            console.print(f"[yellow]warning:[/yellow] {warning.message}")
