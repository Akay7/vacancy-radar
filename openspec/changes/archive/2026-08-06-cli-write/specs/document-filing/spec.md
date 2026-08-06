## ADDED Requirements

### Requirement: add_document refuses to overwrite an existing path
`add_document` SHALL raise a typed error and write nothing when its
derived path already exists on disk.

#### Scenario: A derived path collision without a free suffix is impossible to reach silently
- **GIVEN** a vacancy directory whose `documents/` already contains a
  file at every filename `add_document`'s collision-suffixing would
  try for a given date/kind/title
- **WHEN** `add_document` is called with that date, kind, and title
- **THEN** it raises a typed error rather than overwriting any existing
  file

### Requirement: a title is safely reduced to a derived filename
`add_document` SHALL derive its file's name from `date`, `kind`, and
`title` alone, never from a caller-supplied path, and the derived name
SHALL always resolve inside the target vacancy's `documents/`
directory regardless of `title`'s content.

#### Scenario: A title containing path separators and .. stays inside the target directory
- **WHEN** `add_document` is called with a `title` containing `/`,
  `\`, and `..` segments
- **THEN** the returned path lies inside that vacancy's `documents/`
  directory, and no file is created anywhere else in the vault

### Requirement: add_document's document is searchable without a separate reindex
`add_document` SHALL refresh the index for the document it creates
before returning.

#### Scenario: A filed document is retrievable by search immediately after add_document
- **WHEN** `add_document` is called and returns successfully (not the
  external_id-dedupe path)
- **THEN** a `search` call in the same process against its content
  returns it as a hit, without an intervening `reindex` call

### Requirement: add_document dedupes by external_id, not by content
`add_document` SHALL, when `external_id` is given and already matches a
document filed under the same vacancy, return that document's existing
path and create no new file. A different `external_id` SHALL always
result in a new document, regardless of content similarity.

#### Scenario: Re-filing the same external_id is a no-op
- **GIVEN** a vacancy with one document already filed under
  `external_id="thread-123"`
- **WHEN** `add_document` is called again for that vacancy with
  `external_id="thread-123"`
- **THEN** the previously filed document's path is returned and no new
  file is created

#### Scenario: The same content under a different external_id creates a second document
- **GIVEN** a vacancy with one document already filed under
  `external_id="thread-123"`
- **WHEN** `add_document` is called with the same `content` and `title`
  but `external_id="thread-456"`
- **THEN** a second, distinct document is created

### Requirement: writes stay contained inside the vault
Every path this change's functions write to SHALL be verified inside
the vault (via the stage 2 containment check) before any write touches
the filesystem; a path that would resolve outside the vault SHALL raise
a typed error instead.

#### Scenario: A write attempt outside the vault raises before touching the filesystem
- **WHEN** a write function is given inputs that, absent the
  containment check, would resolve a target path outside the vault
- **THEN** a typed error is raised and no file is created or modified
  anywhere

### Requirement: no function in this change deletes vault content
No function added by this change SHALL remove, truncate in place, or
overwrite the content of any existing vault file (`vacancy.md`'s
frontmatter update via `set_status` is the sole, explicitly documented
exception, and it preserves the file's body byte for byte).

#### Scenario: A sequence of writes never reduces the vault's file set
- **GIVEN** a vault with an existing set of files
- **WHEN** any combination of `append_note`, `set_status`,
  `add_document`, `create_vacancy`, and `reindex` calls is made against
  it
- **THEN** every file present before the calls is still present
  afterward, and no existing file's body content (other than
  `vacancy.md`'s via `set_status`) has changed

### Requirement: a failed write leaves no partial file
Every file this change creates or updates SHALL be written atomically
— never observable as a truncated or partially written file, whether
the write succeeds or fails partway.

#### Scenario: A write that fails partway leaves the target path either absent or fully written
- **WHEN** a write operation is interrupted or fails after starting to
  produce content but before it would normally complete
- **THEN** the target path is either absent (if it didn't exist
  before) or holds its prior, complete content (if it did) — never a
  truncated or partial file
