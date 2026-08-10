## ADDED Requirements

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
