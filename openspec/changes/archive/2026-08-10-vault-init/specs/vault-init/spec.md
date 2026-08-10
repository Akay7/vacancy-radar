## ADDED Requirements

### Requirement: resolve_target_path resolves by explicit-argument, then env-var, precedence, without requiring the target to exist
`config.resolve_target_path` SHALL accept an optional explicit path
argument. When given, it SHALL take precedence over the `VAULT_PATH`
environment variable. When omitted (or `None`) and `VAULT_PATH` is
set, the environment variable SHALL be used. When neither is present,
a `VaultNotConfiguredError` SHALL be raised. Unlike
`resolve_vault_path`, it SHALL NOT require the resolved path to exist,
be a directory, or carry a `.vacancy-radar/` marker.

#### Scenario: explicit argument overrides VAULT_PATH
- **GIVEN** `VAULT_PATH` is set to one path and an explicit path
  argument points to a different path
- **WHEN** `resolve_target_path` is called with that explicit argument
- **THEN** the explicit argument's path is resolved and returned,
  ignoring `VAULT_PATH`

#### Scenario: VAULT_PATH is used when no argument is given
- **GIVEN** `VAULT_PATH` is set and no explicit argument is given
- **WHEN** `resolve_target_path` is called with no argument
- **THEN** the path from `VAULT_PATH` is resolved and returned

#### Scenario: neither present raises VaultNotConfiguredError
- **GIVEN** `VAULT_PATH` is unset and no explicit argument is given
- **WHEN** `resolve_target_path` is called
- **THEN** a `VaultNotConfiguredError` is raised

#### Scenario: a path that does not exist yet is returned, not rejected
- **GIVEN** a path with no file or directory at that location
- **WHEN** `resolve_target_path` is called with that path
- **THEN** the path is resolved (absolute) and returned, and no
  exception is raised

### Requirement: init_vault creates the marker directory under a path that doesn't exist yet
`core.init_vault` SHALL, when its resolved target path does not exist,
create it (including any missing parent directories) and a
`.vacancy-radar/` marker directory inside it, and report `created=True`.

#### Scenario: A brand-new path gets created with its marker
- **GIVEN** a path with nothing at that location, including missing
  parent directories
- **WHEN** `core.init_vault` is called with that path
- **THEN** the path exists afterward as a directory, its
  `.vacancy-radar/` marker directory exists, and the result reports
  `created=True`

### Requirement: init_vault adds the marker to an existing, non-vault directory without touching its contents
`core.init_vault` SHALL, when its resolved target path already exists
as a directory but has no `.vacancy-radar/` marker, create the marker
and leave every other file or directory already present unchanged,
reporting `created=True`.

#### Scenario: An existing directory's contents survive being adopted
- **GIVEN** a directory that already exists and already contains files
  unrelated to any vault
- **WHEN** `core.init_vault` is called with that directory's path
- **THEN** the `.vacancy-radar/` marker directory now exists inside
  it, every previously-existing file's content is unchanged, and the
  result reports `created=True`

### Requirement: init_vault is a no-op on an already-initialized vault
`core.init_vault` SHALL, when its resolved target path already
satisfies `resolve_vault_path` (exists, is a directory, already carries
the marker), make no filesystem change and report `created=False`.

#### Scenario: Re-running init against an already-initialized vault changes nothing
- **GIVEN** a path that is already a valid vault
- **WHEN** `core.init_vault` is called with that path
- **THEN** no file or directory under that path is created, modified,
  or removed, and the result reports `created=False`

### Requirement: init_vault rejects a target that exists as a file
`core.init_vault` SHALL, when its resolved target path exists as a
regular file rather than a directory, raise a typed error and make no
filesystem change.

#### Scenario: A file at the target path is rejected without being touched
- **GIVEN** a path pointing at an existing regular file
- **WHEN** `core.init_vault` is called with that path
- **THEN** a typed error is raised, and that file's content is
  unchanged and no new file or directory is created

### Requirement: init_vault uses the same explicit-then-VAULT_PATH precedence as every other core.py function
`core.init_vault` SHALL resolve its target path via
`config.resolve_target_path`'s precedence: an explicit `path` argument
takes priority over `VAULT_PATH`; when neither is given, a typed error
naming both mechanisms is raised and no filesystem change is made.

#### Scenario: An explicit path argument is used over VAULT_PATH
- **GIVEN** `VAULT_PATH` set to one path and an explicit `path`
  argument pointing elsewhere
- **WHEN** `core.init_vault` is called with that explicit argument
- **THEN** the vault is created at the explicit argument's path, not
  at `VAULT_PATH`'s

#### Scenario: VAULT_PATH is used when no explicit path is given
- **GIVEN** `VAULT_PATH` set to a path with nothing at that location
  and no explicit argument given
- **WHEN** `core.init_vault` is called with no argument
- **THEN** the vault is created at the `VAULT_PATH` location

#### Scenario: Neither present raises a typed error naming both mechanisms
- **GIVEN** `VAULT_PATH` unset and no explicit argument given
- **WHEN** `core.init_vault` is called
- **THEN** a `VaultNotConfiguredError` is raised and no filesystem
  change is made

### Requirement: the init CLI command creates a vault and reports the outcome
`vacancy-radar init [PATH]` SHALL create a vault at `PATH` (or
`VAULT_PATH` when `PATH` is omitted), printing an outcome distinguishing
a freshly created vault from an already-initialized one, and exit 0 in
both cases.

#### Scenario: init on a new path reports created
- **WHEN** `vacancy-radar init <path>` is run against a path with
  nothing at that location
- **THEN** the command exits 0 and its output reports the vault as
  created at `<path>`

#### Scenario: init on an already-initialized vault reports no error
- **GIVEN** a path that is already a valid vault
- **WHEN** `vacancy-radar init <path>` is run against it
- **THEN** the command exits 0 and its output distinguishes this
  outcome from a fresh creation, without printing an error

### Requirement: init --json reports path and outcome in the standard write-command shape
`vacancy-radar init --json` SHALL emit a JSON document naming the
resolved path and an outcome value distinguishing "created" from
"already initialized," in the same shape `new`/`add`/`note`/`status
set` already use for their own `--json` output.

#### Scenario: init --json reports created
- **WHEN** `vacancy-radar init <path> --json` is run against a path
  with nothing at that location
- **THEN** stdout is valid JSON whose path names `<path>` and whose
  outcome indicates creation

#### Scenario: init --json reports the already-initialized outcome
- **GIVEN** a path that is already a valid vault
- **WHEN** `vacancy-radar init <path> --json` is run against it
- **THEN** stdout is valid JSON whose outcome indicates no change was
  made

### Requirement: a freshly initialized vault is immediately usable by every other command
Every other CLI command and `core.py` function SHALL, when pointed at
a path `core.init_vault` just created, operate on it successfully via
the ordinary `resolve_vault_path` path — no separate setup step beyond
`init` itself.

#### Scenario: list succeeds against a freshly initialized vault
- **WHEN** `vacancy-radar list` is run with `VAULT_PATH` (or an
  equivalent explicit resolution) pointed at a path `core.init_vault`
  just created
- **THEN** the command exits 0 and reports zero vacancies, rather than
  raising `VaultNotFoundError`
