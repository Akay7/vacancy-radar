## Why

The repo has lint/format/test checks defined but they only run in CI
(`.github/workflows/ci.yml`), after a push. There is no local gate, so
formatting, lint, and typo mistakes routinely round-trip through a CI
failure instead of being caught before commit. Adding a `pre-commit`
config closes that loop, and hardening the existing CI workflow ensures
the same checks are enforced consistently for every push and pull
request, including on contributions that skip local hooks.

## What Changes

- Add `pre-commit` as a dev dependency and a `.pre-commit-config.yaml`
  that runs `ruff check --fix`, `ruff format`, and standard hygiene
  hooks (trailing whitespace, end-of-file-fixer, YAML/TOML syntax
  checks) on staged files.
- Document local setup (`uv run pre-commit install`) in `README.md`.
- Replace CI's separate "Lint" (`ruff check`) and "Check formatting"
  (`ruff format --check`) steps in `.github/workflows/ci.yml` with a
  single `uv run pre-commit run --all-files` step, so CI enforces the
  exact same hooks as local commits without running ruff twice. The
  `pytest` step is untouched.
- No changes to application code; this only affects the development
  workflow and CI pipeline.

## Capabilities

### New Capabilities
- `dev-workflow`: Defines the pre-commit hook set contributors run
  locally before committing, and the CI enforcement that mirrors it.

### Modified Capabilities
(none — no existing capability's runtime requirements change)

## Impact

- **New files**: `.pre-commit-config.yaml`
- **Modified files**: `pyproject.toml` (dev dependency group),
  `.github/workflows/ci.yml` (swap lint/format steps for a
  pre-commit step), `README.md` (document hook installation)
- **Dependencies**: adds `pre-commit` to the `dev` dependency group
  (managed via `uv`)
- **Systems**: GitHub Actions CI; local git hooks for contributors
