# mcp-resources

## Purpose
Defines the MCP server's resources — `vacancy-radar://companies` and
`vacancy-radar://statuses` — read-only, tool-call-free views generated live
from vault content and `models.py` data.

## Requirements

### Requirement: the companies resource lists every company in the active vault
`vacancy-radar://companies` SHALL list every company present in the
active vault, each with its slug, display name, and vacancy count, and
SHALL NOT require a tool call to obtain.

#### Scenario: the companies resource lists every fixture-vault company
- **GIVEN** the fixture vault, with a known set of companies
- **WHEN** the `vacancy-radar://companies` resource is read
- **THEN** the response lists every company present in the fixture
  vault, each with its slug, display name, and vacancy count, and lists
  no company absent from the vault

### Requirement: the statuses resource reflects models.py's vocabulary and transition graph
`vacancy-radar://statuses` SHALL list every `Status` member and, for
each, the set of statuses `models.STATUS_TRANSITIONS` permits reaching
from it without `force` — read from `models.py` as data, so the
resource's content changes automatically if `models.py`'s vocabulary or
graph changes, without this change's code being edited.

#### Scenario: the statuses resource lists every Status member with its permitted transitions
- **WHEN** the `vacancy-radar://statuses` resource is read
- **THEN** the response includes every `Status` member, and for each
  one, exactly the set of statuses `models.STATUS_TRANSITIONS[status]`
  names

#### Scenario: the statuses resource reflects an added transition without server code changes
- **GIVEN** a test that monkeypatches `models.STATUS_TRANSITIONS` to
  include an additional permitted transition for one status
- **WHEN** the `vacancy-radar://statuses` resource is read
- **THEN** the response reflects the monkeypatched transition, proving
  the resource is generated from `models.py`'s data at read time, not
  a value copied into the server module
