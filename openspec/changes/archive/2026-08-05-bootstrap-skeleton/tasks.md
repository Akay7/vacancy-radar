## 1. Project files

- [x] 1.1 Write `pyproject.toml`: package `vacancy-radar`, module
      `vacancy_radar`, src layout, hatchling build backend, static
      `version = "0.1.0"`, console script `vacancy-radar = "vacancy_radar.cli:app"`
- [x] 1.2 Add runtime dependencies to `pyproject.toml`: `typer`, `rich`,
      `pydantic` (no `lancedb`, no `fastembed`)
- [x] 1.3 Add `dev` dependency group to `pyproject.toml`: `pytest`,
      `pytest-cov`, `ruff`
- [x] 1.4 Add `[tool.ruff]` config: default line-length (88), lint rules
      `select = ["ALL"]` with per-rule ignores added only as concrete
      false positives show up (T20/flake8-print stays enabled — it
      enforces invariant 5)
- [x] 1.5 Write `.gitignore` covering `.venv`, `__pycache__`,
      `.pytest_cache`, `.ruff_cache`, `dist`, `*.egg-info`, `.index/`,
      `.env`, `vault/`
- [x] 1.6 Add MIT `LICENSE`
- [x] 1.7 Write `README.md` skeleton, including an empty retrieval
      evaluation table with columns `mode | weighting | recall@5`

## 2. CLI version tests, then implementation

- [x] 2.1 Write `tests/test_version.py`: `__version__` is a three-part
      numeric string (regex `^\d+\.\d+\.\d+$`)
- [x] 2.2 Write `tests/test_import.py`: `vacancy_radar` imports
      successfully in an environment where `lancedb` and `fastembed` are
      blocked from import (e.g. via a `sys.meta_path` finder that raises
      `ImportError` for those two module names, installed for the
      duration of the test)
- [x] 2.3 Run tests, confirm they fail (no package exists yet)
- [x] 2.4 Implement `src/vacancy_radar/__init__.py`: `__version__` read
      via `importlib.metadata.version("vacancy-radar")`, falling back to
      `"0.0.0"` on `PackageNotFoundError`
- [x] 2.5 `uv sync --all-groups`, then re-run 2.1–2.2 and confirm they pass

## 3. CLI behavior tests, then implementation

- [x] 3.1 Write `tests/test_cli.py` scenario: `vacancy-radar --version` exits 0 and
      output contains `vacancy_radar.__version__`
- [x] 3.2 Write `tests/test_cli.py` scenario: `vacancy-radar` with no arguments
      exits 0 and output includes usage/help text
- [x] 3.3 Write `tests/test_cli.py` scenario: `vacancy-radar bogus-command` exits
      non-zero
- [x] 3.4 Run tests, confirm they fail (no CLI module exists yet)
- [x] 3.5 Implement `src/vacancy_radar/cli.py`: Typer `app` with an eager
      `--version` callback that prints `vacancy_radar.__version__` and
      exits 0. (Deviation from plan: Typer's `no_args_is_help=True` exits
      2 via `NoArgsIsHelpError`, a `UsageError` subclass — not 0. Handled
      manually instead: `invoke_without_command=True` on the callback,
      checking `ctx.invoked_subcommand is None` and printing
      `ctx.get_help()` with `typer.Exit(code=0)`.)
- [x] 3.6 Re-run 3.1–3.3 and confirm they pass

## 4. CI

- [x] 4.1 Write `.github/workflows/ci.yml`: on push/PR, `uv sync
      --all-groups`, `uv run ruff check .`, `uv run ruff format --check .`,
      `uv run pytest`

## 5. Verification

- [x] 5.1 On a fresh clone/checkout, run `uv sync --all-groups && uv run
      pytest && uv run ruff check .` and confirm all pass
- [x] 5.2 Run `uv run ruff format --check .` and confirm it passes
- [x] 5.3 Run `uv run vacancy-radar --version` and confirm it prints the version
- [x] 5.4 Confirm no `print()` calls exist anywhere under `src/`
      (`ruff check .` catching `T20` covers this, but eyeball it too)
