"""`vacancy-radar` CLI entry point: ingest, sync, reindex, import-fods."""

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


def _print_summary(command: str, summary: RunSummary) -> None:
    print(
        f"{command}: bullets_ingested={summary.bullets_ingested} "
        f"vacancies_created={summary.vacancies_created} "
        f"vacancies_updated={summary.vacancies_updated} "
        f"vacancies_skipped={summary.vacancies_skipped}"
    )
    for invalid in summary.vacancies_invalid:
        print(f"  INVALID: {invalid.folder} — {invalid.reason}", file=sys.stderr)
    for conflict in summary.vacancies_conflicting:
        folders = ", ".join(conflict.folders)
        print(f"  CONFLICT: natural key '{conflict.natural_key}' — {folders}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vacancy-radar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ingest", help="Ingest CV bullets + vacancy folders into Chroma")
    subparsers.add_parser("sync", help="Upsert new/changed vacancy folders since last ingest")
    subparsers.add_parser("reindex", help="Delete the local cache and re-embed from source")

    import_fods = subparsers.add_parser(
        "import-fods", help="One-time convert a Job.fods spreadsheet into vacancy folders"
    )
    import_fods.add_argument("path", help="Path to the .fods file")

    args = parser.parse_args(argv)

    if args.command == "import-fods":
        print("'import-fods' is not implemented yet — see README.md roadmap", file=sys.stderr)
        return 1

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

    _print_summary(args.command, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
