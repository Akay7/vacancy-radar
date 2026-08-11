# release-workflow Specification

## Purpose
Defines how a version of `vacancy-radar` reaches a package index: a
tag-triggered `.github/workflows/release.yml` kept separate from CI, an
agreement check between the tag and the declared version, verification of
the built wheel in a clean environment before anything is uploaded,
Trusted Publishing (OIDC) with no stored credential, a TestPyPI dry-run
path through the same workflow, and the documentation and changelog
obligations that surround a release.

## Requirements

### Requirement: Releases are triggered by a version tag
The repository SHALL contain a GitHub Actions workflow at
`.github/workflows/release.yml` that runs on pushes of tags matching
`v*`. This workflow SHALL be separate from `ci.yml`, and `ci.yml` SHALL
NOT publish anything.

#### Scenario: Pushing a version tag starts a release run
- **WHEN** a tag matching `v*` is pushed to the repository
- **THEN** the release workflow runs

#### Scenario: Ordinary pushes and pull requests do not publish
- **WHEN** a commit is pushed to `main` or a pull request is opened
- **THEN** the release workflow does not run, and no upload to any
  package index is attempted

### Requirement: The tag and the declared version must agree
The release workflow SHALL compare the pushed tag, with a leading `v`
stripped, against the version recorded in the built distribution
metadata, and SHALL fail the run when they differ, before any artifact
is uploaded to a package index.

#### Scenario: Mismatched tag aborts the release
- **GIVEN** `[project].version` in `pyproject.toml` is `0.1.0`
- **WHEN** a tag `v0.2.0` is pushed
- **THEN** the release workflow fails at the version-agreement check
- **THEN** no upload to any package index is attempted

#### Scenario: Matching tag proceeds
- **GIVEN** `[project].version` in `pyproject.toml` is `0.2.0`
- **WHEN** a tag `v0.2.0` is pushed
- **THEN** the version-agreement check passes and the workflow continues
  to the build step

### Requirement: The built artifact is verified in a clean environment before upload
The release workflow SHALL build the distribution once, then install the
built wheel into a fresh environment that has no repository checkout on
its import path and does not resolve from the repository's `uv.lock`,
and SHALL execute the installed console scripts there. The upload step
SHALL depend on this verification succeeding, and SHALL upload the same
artifact that was verified rather than rebuilding it.

#### Scenario: Installed wheel reports the released version
- **GIVEN** the wheel built for tag `vX.Y.Z` is installed into a clean
  environment
- **WHEN** `vacancy-radar --version` is run there
- **THEN** it exits 0 and its output contains `X.Y.Z`

#### Scenario: Installed MCP script is executable
- **GIVEN** the wheel built for the release is installed into a clean
  environment
- **WHEN** `vacancy-radar-mcp --help` is run there
- **THEN** it exits 0

#### Scenario: A wheel whose dependencies do not resolve blocks the release
- **GIVEN** the built wheel declares a dependency set that cannot be
  resolved without the repository's `uv.lock`
- **WHEN** the verification job installs the wheel into a clean
  environment
- **THEN** the verification job fails
- **THEN** the publish job does not run and nothing is uploaded

#### Scenario: The published artifact is the verified artifact
- **GIVEN** a release run that has passed verification
- **WHEN** the publish job runs
- **THEN** it consumes the distribution artifact produced by the build
  job rather than building the project again

### Requirement: Publishing uses Trusted Publishing with no stored credential
The release workflow SHALL authenticate to the package index using
GitHub's OIDC identity (PyPI Trusted Publishing). The publishing job
SHALL request `id-token: write` permission and SHALL run under a named
GitHub Environment. No PyPI API token or password SHALL be stored as a
repository secret or referenced by the workflow.

#### Scenario: Workflow contains no index credential
- **WHEN** `.github/workflows/release.yml` is inspected
- **THEN** it references no secret holding a PyPI token, username, or
  password
- **THEN** the publishing job declares `permissions: id-token: write`

#### Scenario: Publishing is gated on an environment
- **WHEN** the publishing job in `.github/workflows/release.yml` is
  inspected
- **THEN** it declares an `environment` whose name matches the
  environment registered with the index's Trusted Publisher
  configuration

### Requirement: A dry-run release targets TestPyPI through the same workflow
The release workflow SHALL support manual invocation
(`workflow_dispatch`) with an input selecting the target index, offering
at least `testpypi` and `pypi`, and defaulting to `testpypi`. The
dry-run path SHALL execute the same build and verification steps as a
tag-triggered release.

#### Scenario: Manual dispatch defaults to the test index
- **WHEN** the release workflow is dispatched manually without
  overriding the target input
- **THEN** the artifact is uploaded to TestPyPI, not to PyPI

#### Scenario: Dry run exercises the same verification
- **WHEN** the release workflow is dispatched against TestPyPI
- **THEN** the build, version-agreement, and clean-environment
  verification steps run exactly as they do for a tag-triggered release

### Requirement: The release procedure is documented
The repository SHALL contain `docs/releasing.md` documenting the
one-time Trusted Publisher setup for both PyPI and TestPyPI (repository,
workflow filename, and environment names to register), the per-release
steps (version bump, changelog entry, tag, push), and the recovery
procedure when a bad version reaches an index.

#### Scenario: Setup checklist names the exact values to register
- **WHEN** `docs/releasing.md` is read
- **THEN** it states the repository, workflow filename, and environment
  name required by each index's Trusted Publisher configuration

#### Scenario: Recovery procedure rules out re-uploading
- **WHEN** `docs/releasing.md` is read
- **THEN** it states that a published version cannot be replaced, and
  that recovery is to yank the bad version and release a new one

### Requirement: Releases are recorded in a changelog
The repository SHALL contain a `CHANGELOG.md` with a dated entry per
released version, and the release procedure SHALL require the entry for
a version to exist before that version is tagged.

#### Scenario: Changelog covers the released versions
- **WHEN** `CHANGELOG.md` is read
- **THEN** it contains an entry for each released version, and an
  unreleased section for pending changes
