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

### Requirement: Release automation is separate from the CI workflow
The repository SHALL keep release/publish automation in its own workflow
file, distinct from `.github/workflows/ci.yml`. The CI workflow SHALL
continue to run only on pushes to `main` and on pull requests, and SHALL
NOT gain publish, upload, or index-authentication steps.

#### Scenario: CI workflow contains no publishing steps
- **WHEN** `.github/workflows/ci.yml` is inspected
- **THEN** it contains no step that builds and uploads a distribution to
  a package index
- **THEN** it requests no `id-token` permission and declares no
  deployment environment

#### Scenario: CI triggers are unchanged
- **WHEN** `.github/workflows/ci.yml` is inspected
- **THEN** its triggers remain pushes to `main` and pull requests, with
  no tag trigger added

### Requirement: Publishing rights are gated on a protected environment, not a repository secret
Any workflow job that uploads to a package index SHALL run under a named
GitHub Environment and SHALL obtain its upload credential through
GitHub's OIDC identity. The repository SHALL NOT store a package-index
API token, username, or password as a repository or organization secret
for this purpose.

#### Scenario: No index credential is stored or referenced
- **WHEN** the repository's workflows are searched for package-index
  credentials
- **THEN** no workflow references a secret holding an index token,
  username, or password

#### Scenario: Upload jobs declare an environment
- **WHEN** a workflow job that uploads to a package index is inspected
- **THEN** it declares an `environment`, so that reviewer or branch
  restrictions can be attached to releases without editing the workflow
