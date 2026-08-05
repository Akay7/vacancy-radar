## ADDED Requirements

### Requirement: content_hash is a stable sha256 of file bytes
`content_hash(path)` SHALL return the sha256 hex digest of the file's
full byte content. It SHALL NOT read or depend on the file's mtime,
size, or inode — only its bytes.

#### Scenario: content_hash is stable when mtime changes but content does not
- **GIVEN** a file with a known hash
- **WHEN** the file's modification time is updated (e.g. via `touch`)
  without changing its content
- **THEN** `content_hash` returns the same value as before

#### Scenario: content_hash changes when a single byte changes
- **GIVEN** a file with a known hash
- **WHEN** a single byte in the file is changed
- **THEN** `content_hash` returns a different value

#### Scenario: two files with identical content hash identically
- **GIVEN** two distinct files whose byte content is identical
- **WHEN** `content_hash` is called on each
- **THEN** both calls return the same value
