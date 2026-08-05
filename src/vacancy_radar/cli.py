import sys
import tempfile
from pathlib import Path

import typer

import vacancy_radar

app = typer.Typer()


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


@app.command("_eval", hidden=True)
def eval_command() -> None:
    """Private: run stage 5's retrieval eval full sweep against the
    fixture vault and print the resulting report.

    Hidden from `--help` and from the public interface: a development
    tool, replaced outright by the public `eval` command at stage 6 -
    see the eval-harness change's design.md. Imports `eval/` from the
    repo checkout (never shipped in the built wheel), so this only
    works from a plain checkout, not an installed package.
    """
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from eval.run import FULL_SWEEP, load_queries, run_eval  # noqa: PLC0415

    from vacancy_radar.index.build import build_index  # noqa: PLC0415
    from vacancy_radar.index.store import (  # noqa: PLC0415
        default_index_path,
        get_index_handle,
    )
    from vacancy_radar.vault.reader import read_vault  # noqa: PLC0415

    queries = load_queries(repo_root / "eval" / "queries.yaml")
    fixture_vault = repo_root / "tests" / "fixtures" / "vault"

    with tempfile.TemporaryDirectory() as tmp_dir:
        vault_root = Path(tmp_dir)
        index_path = default_index_path(vault_root)
        build_index(read_vault(fixture_vault), index_path)
        index = get_index_handle(vault_root)
        report = run_eval(queries, index, FULL_SWEEP)

    typer.echo(report.to_markdown())
