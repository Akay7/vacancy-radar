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
from vacancy_radar.models import Status
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
