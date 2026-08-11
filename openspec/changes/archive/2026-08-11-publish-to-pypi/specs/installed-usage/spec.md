## ADDED Requirements

### Requirement: The CLI is runnable from the published distribution without a checkout
A user with `uv` installed and no clone of this repository SHALL be able
to run the CLI via `uvx vacancy-radar`, and to install it persistently
via `uv tool install vacancy-radar`. Neither path SHALL require a
`uv.lock`, a `pyproject.toml`, or any file from the repository.

#### Scenario: uvx runs the CLI in a throwaway environment
- **GIVEN** a machine with `uv` installed and no vacancy-radar checkout
- **WHEN** the user runs `uvx vacancy-radar --version`
- **THEN** the published distribution is fetched, and the command exits
  0 printing the distribution's version

#### Scenario: uv tool install exposes a persistent command
- **GIVEN** a machine with `uv` installed and no vacancy-radar checkout
- **WHEN** the user runs `uv tool install vacancy-radar` and then
  `vacancy-radar --version`
- **THEN** both commands exit 0, and the second prints the installed
  version without a `uv run` or `uvx` prefix

### Requirement: The MCP server is reachable from the published distribution
The MCP server SHALL be runnable from a published install as
`uvx --from vacancy-radar vacancy-radar-mcp`. Because the script name
differs from the distribution name, documentation SHALL use the
`--from` form and SHALL NOT present a bare `uvx vacancy-radar-mcp`
invocation.

#### Scenario: The MCP server starts from a published install
- **GIVEN** a machine with `uv` installed and no vacancy-radar checkout
- **WHEN** the user runs
  `uvx --from vacancy-radar vacancy-radar-mcp --vault <path>`
- **THEN** the MCP server starts and speaks JSON-RPC over stdio

#### Scenario: Documentation never shows the bare uvx form for the server
- **WHEN** the README and `docs/` are searched for `vacancy-radar-mcp`
  invocations under `uvx`
- **THEN** every such invocation includes `--from vacancy-radar`

### Requirement: Install documentation leads with the published distribution
The README's install section SHALL present installing the published
distribution as the primary path for users, and the source checkout
(`uv sync --all-groups` plus `uv run`) as the contributor path, clearly
labelled as such. It SHALL state that an installed user omits the
`uv run` prefix shown in the command examples.

#### Scenario: README shows the user path first
- **WHEN** the README's install section is read
- **THEN** `uvx vacancy-radar` and `uv tool install vacancy-radar`
  appear before the `uv sync --all-groups` contributor instructions
- **THEN** the contributor path is labelled as being for working on the
  project

#### Scenario: README sets expectations for the first run
- **WHEN** the README's install section is read
- **THEN** it states that the first run downloads a large dependency set
  and, on first search, an embedding model

### Requirement: MCP client configuration is documented in copy-pasteable form
The README SHALL document wiring the MCP server into an MCP client using
a configuration block that invokes the published distribution, rather
than a path into a local checkout.

#### Scenario: README carries a client config example
- **WHEN** the README's MCP section is read
- **THEN** it contains a client configuration example whose command
  invokes `uvx` with `--from vacancy-radar vacancy-radar-mcp` and passes
  the vault path
