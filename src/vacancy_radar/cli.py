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
