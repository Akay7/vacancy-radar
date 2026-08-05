## ADDED Requirements

### Requirement: Index handles are resolved lazily, keyed by vault path
`get_index_handle(vault_path)` SHALL create a handle on first request
for a given (resolved) vault path and SHALL return the same handle on
every subsequent request for that same path, without creating a
module-level handle at import time.

#### Scenario: a handle is created on first request, not at import
- **GIVEN** the store module freshly imported, with handle creation
  instrumented
- **WHEN** no call to `get_index_handle` has been made yet
- **THEN** no handle has been created

#### Scenario: repeated requests for the same vault path return the same handle
- **GIVEN** a vault path with no handle yet resolved
- **WHEN** `get_index_handle` is called twice with that same path
- **THEN** both calls return the same handle object

#### Scenario: different vault paths resolve to different handles
- **GIVEN** two distinct vault paths
- **WHEN** `get_index_handle` is called once with each
- **THEN** the two calls return distinct handles, each scoped to its
  own vault's index

### Requirement: The index path is excluded from vault traversal and git tracking
The default index path resolved for a vault (`{vault}/.index/`) SHALL
be a name already excluded from vault directory traversal and already
present in the repository's `.gitignore`.

#### Scenario: the resolved index path is a dot-prefixed, skipped name
- **GIVEN** a vault path
- **WHEN** the default index path is resolved for it
- **THEN** the resolved path's directory name is one `vault.paths`'
  traversal-skip rule already excludes from `read_vault`
