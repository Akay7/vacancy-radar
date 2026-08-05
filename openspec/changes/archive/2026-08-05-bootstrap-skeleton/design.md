## Context

vacancy-radar has no code yet — this is the first change in the repository.
Every later stage (vault model, index, retrieval, CLI, MCP server) will be
built on top of whatever package layout and CI gate this change puts in
place, so the choices here are meant to be boring and hard to outgrow
rather than clever.

## Goals / Non-Goals

**Goals:**
- A `uv sync --all-groups && uv run pytest && uv run ruff check .` clean
  checkout, on day one.
- A single console entry point (`vacancy-radar`) that later stages extend with
  subcommands, never replace.
- A lint configuration that mechanically enforces invariant 5 (no stdout
  output outside JSON-RPC) via `T20`, rather than relying on review.
- A dependency floor (`typer`, `rich`, `pydantic`) that keeps import time
  and install size minimal until a later stage has a concrete reason to
  add `lancedb` / `fastembed`.

**Non-Goals:**
- No vault, index, retrieval, core API, or MCP server logic or
  placeholders — those are separate, later changes.
- No pre-commit, tox, Docker, or docs tooling.
- No packaging for PyPI distribution (e.g. no publish workflow) — only
  local installability via `uv`.

## Decisions

**src layout with hatchling.** Keeps `vacancy_radar` unimportable except
via installation, which is what the "package imports without lancedb/
fastembed present" requirement is actually testing — an accidental
`sys.path` import of a flat-layout module would defeat that guarantee.
Hatchling is uv's default backend and needs no extra configuration for a
single-package src layout.

**Typer for the CLI, with an eager `--version` callback.** Typer gives
unknown-command exit-code behavior (non-zero) for free, without any
bespoke argument-parsing code. An eager callback is the standard Typer
pattern for a flag that must run and exit before subcommand resolution is
attempted — it composes cleanly with subcommands added in later stages.
No-args handling is manual rather than via `no_args_is_help=True`: that
flag raises `NoArgsIsHelpError`, a `UsageError` subclass that exits 2,
not 0. Instead, the callback checks `ctx.invoked_subcommand is None` and
prints `ctx.get_help()` before an explicit `typer.Exit(code=0)`.

**Version via `importlib.metadata`, not a hardcoded string.** Reads the
version that was actually installed (from `pyproject.toml` via
hatchling's dynamic version, or `pyproject.toml`'s static version — see
Open Questions) rather than duplicating it in source. Falls back to
`"0.0.0"` under `PackageNotFoundError` so `import vacancy_radar` still
works in an editable/uninstalled tree (e.g. a plain `python -c "import
vacancy_radar"` without `uv sync`), which the "imports without lancedb/
fastembed" requirement exercises without needing the console script.

**ruff for both lint and format check, no separate formatter.** One tool,
one config block, one CI step pattern (`ruff check` then
`ruff format --check`). Lint rules use `select = ["ALL"]` rather than a
curated subset — maximally strict from day one, with per-rule ignores
added only once a concrete false positive is hit, rather than
under-selecting and missing something. `T20` (flake8-print) is included
by `ALL` and is never ignored, since it's what mechanically enforces
invariant 5. Line-length is left at ruff's default (88) rather than
overridden.

**rich as a declared runtime dependency despite no current usage.** Typer
uses it internally for its default help/error rendering, and the CLI
layer is expected to use it directly for user-facing output in the next
CLI-focused stage. Declaring it now (rather than picking it up
transitively) keeps the dependency list an accurate declaration of what
the package actually relies on.

## Risks / Trade-offs

- [Declaring `rich` now with no direct import yet could look like an
  unused dependency] → It's a direct, load-bearing dependency of Typer's
  default rendering path and is named explicitly in scope; a future ruff
  or dependency-audit pass won't need to reconsider it.
- [`__version__` fallback to `"0.0.0"` could mask a real install failure]
  → Acceptable at this stage: the only consumer of `__version__` right
  now is the `--version` flag and its test, both of which run against an
  installed package in CI; the fallback exists solely for the
  "imports without lancedb/fastembed" test running against source.
- [CI only runs on one Python version implicitly via `uv sync`] → Fine for
  a stage-0 skeleton targeting Python 3.12 specifically; revisit if/when
  multi-version support becomes a goal.

## Migration Plan

Greenfield — no existing users or data. Landing this change means: commit
the skeleton, CI turns green on the PR, done. No rollback concerns beyond
reverting the commit.

## Open Questions

- Static vs. dynamic `version` in `pyproject.toml` (hardcoded string vs.
  hatchling's `[tool.hatch.version]` reading from a `_version.py` or git
  tags). Deferred to implementation: a static version string (e.g.
  `"0.1.0"`) is sufficient to satisfy every requirement in this change
  (three-part numeric string, readable via `importlib.metadata`) without
  committing to a version-bumping workflow this stage doesn't need.
