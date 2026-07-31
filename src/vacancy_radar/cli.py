"""`vacancy-radar` CLI entry point: ingest, sync, reindex, import-fods."""

import argparse
import sys


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

    print(f"'{args.command}' is not implemented yet — see README.md roadmap", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
