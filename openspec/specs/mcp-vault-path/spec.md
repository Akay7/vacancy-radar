# mcp-vault-path

## Purpose
Defines how the MCP server resolves the active vault path at startup — an
explicit `--vault` argument, falling back to `VAULT_PATH`, failing
initialization naming both mechanisms when neither is present, and
validating the resolved path the same way every other `core.py` caller
does.

## Requirements

### Requirement: an explicit --vault argument determines the active vault
The server SHALL, when started with an explicit `--vault` argument, use
that path as the active vault for every tool call, resource read, and
prompt for the life of the process.

#### Scenario: --vault is used when given
- **GIVEN** the server is started with `--vault /path/to/vault-a`
- **WHEN** a tool call requiring the vault path is made
- **THEN** the call resolves against `/path/to/vault-a`

### Requirement: VAULT_PATH is used when --vault is absent
The server SHALL, when started without `--vault`, use the `VAULT_PATH`
environment variable as the active vault.

#### Scenario: VAULT_PATH is used when --vault is absent
- **GIVEN** the server is started without `--vault`, with
  `VAULT_PATH=/path/to/vault-env` set
- **WHEN** a tool call requiring the vault path is made
- **THEN** the call resolves against `/path/to/vault-env`

### Requirement: no vault mechanism present fails initialization, naming both --vault and VAULT_PATH
The server SHALL, when `--vault` is absent and `VAULT_PATH` is unset,
fail during initialization with a message naming both the `--vault`
argument and the `VAULT_PATH` environment variable.

#### Scenario: startup fails naming both mechanisms
- **GIVEN** the server is started without `--vault` and without
  `VAULT_PATH` set
- **WHEN** the server initializes
- **THEN** initialization fails with a message that names both
  `--vault` and `VAULT_PATH`

### Requirement: the resolved vault path is validated the same way every other caller's is
The server SHALL validate the resolved vault path (exists, is a
directory, contains the `.vacancy-radar/` marker) using the same check
every other `core.py` caller already relies on, rather than a separate
validation rule of its own.

#### Scenario: a path that fails vault validation fails initialization
- **GIVEN** the server is started with `--vault` pointing at a
  directory with no `.vacancy-radar/` marker
- **WHEN** the server initializes
- **THEN** initialization fails with the same typed error
  `config.resolve_vault_path` raises for an invalid vault path
