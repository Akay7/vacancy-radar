# package-skeleton

## Purpose
TBD — captured from the `bootstrap-skeleton` change. Defines the baseline
packaging and CLI behavior for the `vacancy-radar` project: how the CLI
reports its version, handles no-argument and unknown-command invocations,
and how the `vacancy_radar` package exposes its version and stays
importable without the (later-stage) search-stack dependencies.

## Requirements

### Requirement: CLI reports its version
The `vacancy-radar` CLI SHALL accept a `--version` flag that prints the package
version and exits successfully, without requiring a subcommand.

#### Scenario: --version exits 0 and prints the version
- **GIVEN** the `vacancy-radar` package is installed
- **WHEN** the CLI is invoked with `--version`
- **THEN** it exits with code 0
- **THEN** its output contains the value of `vacancy_radar.__version__`

### Requirement: CLI shows usage when invoked with no arguments
The `vacancy-radar` CLI SHALL print usage/help text and exit successfully when
invoked with no arguments, rather than erroring or hanging.

#### Scenario: no arguments prints usage and exits 0
- **GIVEN** the `vacancy-radar` package is installed
- **WHEN** the CLI is invoked with no arguments
- **THEN** it exits with code 0
- **THEN** its output includes usage/help text

### Requirement: CLI rejects unknown commands
The `vacancy-radar` CLI SHALL exit with a non-zero status when invoked with a
command it does not recognize.

#### Scenario: unknown command exits non-zero
- **GIVEN** the `vacancy-radar` package is installed
- **WHEN** the CLI is invoked with a command name that does not exist
- **THEN** it exits with a non-zero status code

### Requirement: Package exposes a well-formed version
The `vacancy_radar` module SHALL expose a `__version__` attribute that is
a three-part numeric version string (e.g. `"0.1.0"`).

#### Scenario: __version__ is a three-part numeric string
- **GIVEN** the `vacancy_radar` package is imported
- **WHEN** `vacancy_radar.__version__` is read
- **THEN** it matches a three-part numeric pattern, e.g. `^\d+\.\d+\.\d+$`

### Requirement: Package imports without search-stack dependencies
The `vacancy_radar` package SHALL be importable in an environment that
has neither `lancedb` nor `fastembed` installed, since those are deferred
to a later stage and must not become an accidental import-time
dependency of this stage.

#### Scenario: import succeeds without lancedb or fastembed present
- **GIVEN** an environment where `lancedb` and `fastembed` are not
  installed (and, e.g., import-blocked via `sys.modules`/meta path
  interception in the test)
- **WHEN** `vacancy_radar` is imported
- **THEN** the import succeeds without raising `ImportError` or
  `ModuleNotFoundError`

### Requirement: Installed distribution reports its distribution version
`vacancy_radar.__version__` SHALL equal the version recorded in the
installed distribution's metadata whenever the `vacancy-radar`
distribution is installed, and SHALL NOT be the not-installed fallback
value in that case. The `vacancy-radar --version` command SHALL print
that same value.

The `"0.0.0"` fallback remains correct behavior for an uninstalled
source tree; this requirement constrains only the installed case.

#### Scenario: __version__ matches installed distribution metadata
- **GIVEN** the `vacancy-radar` distribution is installed in the
  environment
- **WHEN** `vacancy_radar.__version__` is read
- **THEN** it equals `importlib.metadata.version("vacancy-radar")`
- **THEN** it is not `"0.0.0"`

#### Scenario: CLI --version agrees with distribution metadata
- **GIVEN** the `vacancy-radar` distribution is installed in the
  environment
- **WHEN** `vacancy-radar --version` is run
- **THEN** it exits 0 and its output contains
  `importlib.metadata.version("vacancy-radar")`
