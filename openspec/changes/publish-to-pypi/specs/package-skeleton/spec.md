## ADDED Requirements

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
