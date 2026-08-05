# dev-workflow Specification

## Purpose
TBD - created by syncing change add-precommit-and-ci-tests. Update Purpose after archive.

## Requirements

### Requirement: Pre-commit hooks enforce lint and format on commit
The repository SHALL provide a `.pre-commit-config.yaml` that runs
`ruff check` and `ruff format --check` (or their pre-commit-native
equivalents) against staged files, plus standard file-hygiene hooks
(trailing whitespace, end-of-file fixer, YAML/TOML syntax checks,
merge-conflict markers).

#### Scenario: Committing a lint violation is blocked locally
- **GIVEN** a contributor has run `uv run pre-commit install` in this
  repo
- **WHEN** they `git commit` a Python file containing a ruff lint
  violation
- **THEN** the commit is aborted and the ruff hook reports the
  violation

#### Scenario: Committing malformed YAML is blocked locally
- **GIVEN** a contributor has run `uv run pre-commit install` in this
  repo
- **WHEN** they `git commit` a syntactically invalid YAML file
- **THEN** the commit is aborted and the `check-yaml` hook reports the
  error

### Requirement: pre-commit is installable via the project's dependency manager
The `pre-commit` tool SHALL be declared in the `dev` dependency group
of `pyproject.toml`, so `uv sync --all-groups` makes `pre-commit`
available without a separate global install.

#### Scenario: pre-commit is available after syncing dev dependencies
- **GIVEN** a clean checkout of the repository
- **WHEN** a contributor runs `uv sync --all-groups`
- **THEN** `uv run pre-commit --version` succeeds

### Requirement: CI enforces the same hooks as local pre-commit, without duplicating them
The GitHub Actions CI workflow SHALL run `pre-commit run --all-files`
against every push to `main` and every pull request, using the same
`.pre-commit-config.yaml` that runs locally, in place of separately
invoking `ruff check` and `ruff format --check`. The `pytest` step
SHALL remain a distinct step, unaffected by this change.

#### Scenario: A pre-commit violation fails CI even if tests pass
- **GIVEN** a pull request whose code passes `pytest` but violates a
  configured pre-commit hook (e.g. unformatted code)
- **WHEN** CI runs on that pull request
- **THEN** the `pre-commit run --all-files` step fails, and the
  workflow does not proceed to report overall success

#### Scenario: CI does not run ruff twice
- **GIVEN** the CI workflow file `.github/workflows/ci.yml`
- **WHEN** its steps are inspected
- **THEN** there is exactly one step that invokes `ruff check` and
  exactly one step that invokes `ruff format --check`, both by way of
  the `pre-commit run --all-files` step, with no separate standalone
  `ruff check`/`ruff format --check` steps remaining

#### Scenario: pytest step is unaffected
- **GIVEN** a pull request that passes all pre-commit hooks and all
  tests
- **WHEN** CI runs on that pull request
- **THEN** both the `pre-commit run --all-files` step and the
  existing `pytest` step report success
