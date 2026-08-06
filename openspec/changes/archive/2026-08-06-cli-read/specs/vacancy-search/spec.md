## ADDED Requirements

### Requirement: core.search resolves the vault and delegates to index.search.search
`core.search(...)` SHALL resolve the vault (explicit path or
`VAULT_PATH`, via the same precedence `resolve_vault_path` uses),
obtain its index handle, and pass the query and every filter argument
through to `index.search.search` unchanged — never altering ranking,
fusion, or predicate behavior.

#### Scenario: core.search returns the same hits index.search.search would for the same arguments
- **WHEN** `core.search` is called with a query and filters against a
  resolved vault
- **THEN** the returned hits match what calling `index.search.search`
  directly, with the same arguments and index handle, would return

### Requirement: core.search attaches an index-freshness warning when the index is stale
`core.search(...)` SHALL run the index-freshness check against the
resolved vault and index, and attach any resulting warning to its
result — without raising and without altering the hits themselves.

#### Scenario: search against an index missing documents present in the vault returns results plus a staleness warning naming the count
- **GIVEN** a vault with documents added after the index was last
  built
- **WHEN** `core.search` is called against that vault
- **THEN** it returns the hits the stale index can produce, plus a
  warning naming how many vault documents are missing from the index

### Requirement: core.search never raises for staleness
`core.search(...)` SHALL propagate only `index.search.search`'s own
typed errors (e.g. an empty query or a negative limit); the
freshness check itself SHALL NOT be a source of raised exceptions.

#### Scenario: A stale index does not raise
- **GIVEN** a stale index
- **WHEN** `core.search` is called with an otherwise-valid query
- **THEN** no exception is raised
