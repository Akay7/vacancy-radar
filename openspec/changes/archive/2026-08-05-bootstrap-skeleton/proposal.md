## Why

vacancy-radar has no installable package yet. Every later stage (vault
model, index, retrieval, CLI, MCP server) needs a working package skeleton
to build on: a real `pyproject.toml`, an importable module, a CLI entry
point, and CI that enforces the project's invariants (lint, tests, and —
via the linter — the no-stdout-output rule) from the very first commit.

## What Changes

- Add `pyproject.toml`: package `vacancy-radar`, module `vacancy_radar`,
  src layout, hatchling backend, console script `vacancy-radar` ->
  `vacancy_radar.cli:app`.
- Runtime dependencies limited to `typer`, `rich`, `pydantic`. LanceDB and
  fastembed are deliberately not added yet.
- Add a `dev` dependency group: `pytest`, `pytest-cov`, `ruff`.
- Add `src/vacancy_radar/__init__.py` exposing `__version__`, read via
  `importlib.metadata` with a fallback to `"0.0.0"` when the package isn't
  installed.
- Add `src/vacancy_radar/cli.py`: a Typer app that prints usage and exits
  0 when invoked with no arguments, plus an eager `--version` callback.
- Add ruff configuration with `select = ["ALL"]` (default line-length)
  including the `T20` (flake8-print) rule, so the "diagnostics only to
  stderr" invariant is enforced by the linter from day one.
- Add `.gitignore` covering `.venv`, `__pycache__`, `.pytest_cache`,
  `.ruff_cache`, `dist`, `*.egg-info`, `.index/`, `.env`, `vault/`.
- Add an MIT `LICENSE`.
- Add a README skeleton, including an intentionally empty retrieval
  evaluation table (`mode | weighting | recall@5`) to be filled in at the
  eval-harness stage.
- Add GitHub Actions CI: `uv sync`, `ruff check`, `ruff format --check`,
  `pytest`.
- Add a test suite covering the CLI's observable behavior (`--version`,
  no-args, unknown command) and the shape of `__version__`.

## Capabilities

### New Capabilities

- `package-skeleton`: an installable, importable `vacancy_radar` package
  with a `vacancy-radar` CLI entry point exposing `--version` and standard Typer
  usage/error behavior, versioned via package metadata.

### Modified Capabilities

(none — this is the first change in the repository)

## Impact

- New files only: `pyproject.toml`, `src/vacancy_radar/__init__.py`,
  `src/vacancy_radar/cli.py`, `tests/`, `.gitignore`, `LICENSE`, `README.md`,
  `.github/workflows/ci.yml`.
- No vault, index, retrieval, core API, or MCP server code — those are
  later stages and are explicitly out of scope here.
- Establishes the dependency floor (typer, rich, pydantic only) that later
  stages must respect until they explicitly add LanceDB/fastembed.
