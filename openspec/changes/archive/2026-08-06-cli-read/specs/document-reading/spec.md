## ADDED Requirements

### Requirement: read_document returns full file content for a valid vault path
`read_document(path)` SHALL return the full text of `path` when it is
a file within the configured vault.

#### Scenario: A valid vault path returns file content
- **WHEN** `read_document` is called with the path of a real file
  inside the vault
- **THEN** the returned `DocumentContent` contains that file's full
  text

### Requirement: read_document rejects any path outside the vault
`read_document(path)` SHALL raise a typed error, using the same
containment check `vault.paths.is_within` uses, when `path` resolves
outside the configured vault.

#### Scenario: A path outside the vault raises, using the stage 2 containment check
- **WHEN** `read_document` is called with a path that resolves outside
  the vault
- **THEN** a typed error is raised and no file content is returned

### Requirement: read_document rejects a path traversing via ..
`read_document(path)` SHALL raise the same typed error for a path
that lexically stays inside the vault but traverses outside it via
`..` segments before resolution.

#### Scenario: A path traversing via .. raises
- **WHEN** `read_document` is called with a path containing `..`
  segments that resolve outside the vault
- **THEN** a typed error is raised and no file content is returned

### Requirement: read_document raises a typed error naming a nonexistent path
`read_document(path)` SHALL raise a typed error identifying `path`
when `path` is within the vault but does not exist (or is not a
file).

#### Scenario: A nonexistent path raises a typed error naming the path
- **WHEN** `read_document` is called with a path inside the vault that
  does not exist
- **THEN** a typed error is raised whose message or attributes name
  that path
