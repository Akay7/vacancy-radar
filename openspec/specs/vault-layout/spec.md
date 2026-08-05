# vault-layout Specification

## Purpose
TBD - created by openspec-sync-specs during change vault-reader. Update Purpose after archive.

## Requirements

### Requirement: Vault layout is expressed as constants and path helpers
`vault/paths.py` SHALL define the canonical vault tree as constants and
helper functions, matching the layout stage 1's fixture generator
writes: `{vault}/{company_slug}/_company.md`,
`{vault}/{company_slug}/{vacancy_id}/vacancy.md`,
`{vault}/{company_slug}/{vacancy_id}/documents/*`. Every module in this
change SHALL derive paths from these helpers rather than hard-coding
directory names, so a future layout change touches one file.

#### Scenario: company markdown path helper matches the generated fixture layout
- **GIVEN** a vault root and a company slug present in the fixture
  vault
- **WHEN** the company markdown path helper is called with that root
  and slug
- **THEN** the returned path matches the actual `_company.md` path in
  the fixture vault for that company

#### Scenario: vacancy markdown and documents-directory helpers match the generated fixture layout
- **GIVEN** a vault root, a company slug, and a vacancy id present in
  the fixture vault
- **WHEN** the vacancy markdown path helper and the documents-directory
  helper are called with that root, slug, and id
- **THEN** the returned paths match the actual `vacancy.md` path and
  `documents/` directory for that vacancy in the fixture vault

### Requirement: is_within rejects paths that escape the vault root
`is_within(vault, path)` SHALL return `True` only when `path`, once
resolved (symlinks followed, `..` segments collapsed), is the vault
root or a descendant of it. It SHALL return `False` for a path that
escapes via `..` segments and for a path that stays lexically inside
the vault but is (or passes through) a symlink resolving outside the
vault root.

#### Scenario: is_within rejects a path escaping via ..
- **GIVEN** a vault root and a path constructed with `..` segments that
  resolve to a location outside the vault root
- **WHEN** `is_within` is called with the vault root and that path
- **THEN** it returns `False`

#### Scenario: is_within rejects a symlink inside the vault pointing outside it
- **GIVEN** a vault containing a symlink whose target resolves outside
  the vault root
- **WHEN** `is_within` is called with the vault root and the symlink's
  path
- **THEN** it returns `False`

#### Scenario: is_within accepts an ordinary path inside the vault
- **GIVEN** a vault root and a path to a real file inside it, with no
  symlinks or `..` segments involved
- **WHEN** `is_within` is called with the vault root and that path
- **THEN** it returns `True`

### Requirement: Directory traversal terminates on a symlink loop
Directory traversal SHALL track each directory's resolved real path
before descending into it, and SHALL skip a directory whose resolved
real path was already visited in the current traversal rather than
descend into it. This applies to `read_vault` and to any helper that
walks directories.

#### Scenario: a symlink loop terminates rather than recursing forever
- **GIVEN** a vault containing a symlinked directory that (directly or
  transitively) points back to one of its own ancestor directories
- **WHEN** the vault is traversed
- **THEN** traversal completes and returns, rather than recursing
  without bound
