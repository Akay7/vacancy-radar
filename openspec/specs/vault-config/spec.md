# vault-config Specification

## Purpose
TBD - created by openspec-sync-specs during change vault-reader. Update Purpose after archive.

## Requirements

### Requirement: Vault path resolves by explicit-argument, then env-var, precedence
`resolve_vault_path` SHALL accept an optional explicit path argument.
When given, it SHALL take precedence over the `VAULT_PATH` environment
variable. When omitted (or `None`) and `VAULT_PATH` is set, the
environment variable SHALL be used. When neither is present, a
`VaultNotConfiguredError` SHALL be raised. The explicit-argument
parameter is the seam a future MCP-roots-based caller (stage 8) will
use to pass a client-supplied root without changing this function's
signature.

#### Scenario: explicit argument overrides VAULT_PATH
- **GIVEN** `VAULT_PATH` is set to one directory and an explicit path
  argument points to a different, valid vault directory
- **WHEN** `resolve_vault_path` is called with that explicit argument
- **THEN** the explicit argument's path is resolved and returned,
  ignoring `VAULT_PATH`

#### Scenario: VAULT_PATH is used when no argument is given
- **GIVEN** `VAULT_PATH` is set to a valid vault directory and no
  explicit argument is given
- **WHEN** `resolve_vault_path` is called with no argument
- **THEN** the path from `VAULT_PATH` is resolved and returned

#### Scenario: neither present raises VaultNotConfiguredError
- **GIVEN** `VAULT_PATH` is unset and no explicit argument is given
- **WHEN** `resolve_vault_path` is called
- **THEN** a `VaultNotConfiguredError` is raised

### Requirement: Resolved vault path is absolute, exists, and carries a vault marker
`resolve_vault_path` SHALL return an absolute path, even when its input
was relative. It SHALL verify the path exists, is a directory, and
contains a `.vacancy-radar/` marker directory at its root, raising
`VaultNotFoundError` otherwise with a message stating what was
expected.

#### Scenario: a path that exists but has no vault marker raises VaultNotFoundError
- **GIVEN** a path to an existing directory with no `.vacancy-radar/`
  marker inside it
- **WHEN** `resolve_vault_path` is called with that path
- **THEN** a `VaultNotFoundError` is raised
- **THEN** the error message states that a `.vacancy-radar/` marker
  directory was expected and not found

#### Scenario: a nonexistent path raises VaultNotFoundError
- **GIVEN** a path that does not exist on disk
- **WHEN** `resolve_vault_path` is called with that path
- **THEN** a `VaultNotFoundError` is raised

#### Scenario: a path pointing at a file, not a directory, raises VaultNotFoundError
- **GIVEN** a path pointing at an existing regular file
- **WHEN** `resolve_vault_path` is called with that path
- **THEN** a `VaultNotFoundError` is raised

#### Scenario: the resolved path is absolute even when the input was relative
- **GIVEN** a relative path (relative to the current working directory)
  to a valid vault directory
- **WHEN** `resolve_vault_path` is called with that relative path
- **THEN** the returned path is absolute
