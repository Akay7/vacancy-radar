"""`vacancy-radar` CLI entry point: ingest, sync, reindex, serve, import-fods."""

import argparse
import os
import sys
from pathlib import Path

from vacancy_radar import ingest
from vacancy_radar.ingest import RunSummary


def _dirs_from_env() -> tuple[Path, Path]:
    cv_dir = Path(os.environ.get("CV_DIR", "data/example"))
    vacancy_dir = Path(os.environ.get("VACANCY_DIR", "data/example/vacancies"))
    return cv_dir, vacancy_dir


_COMMAND_VERBS = {"ingest": "Ingesting", "sync": "Syncing", "reindex": "Reindexing"}


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _print_summary(
    command: str, cv_dir: Path, vacancy_dir: Path, summary: RunSummary
) -> None:
    verb = _COMMAND_VERBS.get(command, command.capitalize())
    print(f"{verb} from:")
    print(f"  CV_DIR:      {cv_dir}")
    print(f"  VACANCY_DIR: {vacancy_dir}")
    print()
    print(f"Ingested {_plural(summary.bullets_ingested, 'CV bullet', 'CV bullets')}")
    print(f"Created {_plural(summary.vacancies_created, 'new vacancy', 'new vacancies')}")
    print(f"Updated {_plural(summary.vacancies_updated, 'vacancy', 'vacancies')}")
    skipped = _plural(summary.vacancies_skipped, "unchanged vacancy", "unchanged vacancies")
    print(f"Skipped {skipped}")

    for invalid in summary.vacancies_invalid:
        print(f"  Invalid folder: {invalid.folder} — {invalid.reason}", file=sys.stderr)
    for conflict in summary.vacancies_conflicting:
        folders = ", ".join(conflict.folders)
        print(
            f"  Conflict: natural key '{conflict.natural_key}' shared by: {folders}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vacancy-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ingest", help="Ingest CV bullets + vacancy folders into Chroma")
    subparsers.add_parser("sync", help="Upsert new/changed vacancy folders since last ingest")
    subparsers.add_parser("reindex", help="Delete the local cache and re-embed from source")

    serve = subparsers.add_parser("serve", help="Run the web server (paste-a-posting + upload UI)")
    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Binds to localhost only by default; pass --host 0.0.0.0 to accept "
        "connections from other hosts (e.g. via Docker port mapping)",
    )
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    serve.add_argument("--reload", action="store_true", help="Auto-reload on source changes")

    import_fods = subparsers.add_parser(
        "import-fods", help="One-time convert a Job.fods spreadsheet into vacancy folders"
    )
    import_fods.add_argument("path", help="Path to the .fods file")

    args = parser.parse_args(argv)

    if args.command == "import-fods":
        print("'import-fods' is not implemented yet — see README.md roadmap", file=sys.stderr)
        return 1

    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "vacancy_radar.api:app", host=args.host, port=args.port, reload=args.reload
        )
        return 0

    cv_dir, vacancy_dir = _dirs_from_env()

    if not vacancy_dir.is_dir():
        print(
            f"error: VACANCY_DIR '{vacancy_dir}' does not exist — check your VACANCY_DIR "
            "configuration (see .env.example). A missing CV_DIR is tolerated (nothing to "
            "ground reports in yet), but without vacancy history there is nothing to ingest.",
            file=sys.stderr,
        )
        return 1

    if args.command == "ingest":
        summary = ingest.run_ingest(cv_dir, vacancy_dir, incremental=False)
    elif args.command == "sync":
        summary = ingest.run_ingest(cv_dir, vacancy_dir, incremental=True)
    else:
        summary = ingest.reindex(cv_dir, vacancy_dir)

    _print_summary(args.command, cv_dir, vacancy_dir, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
