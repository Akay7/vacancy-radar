## ADDED Requirements

### Requirement: reindex wraps stage 3's incremental build over a fresh snapshot
`reindex(force=False)` SHALL re-read the vault into a fresh
`VaultSnapshot` and run stage 3's `build_index` against it, returning
the resulting `IndexReport` unchanged.

#### Scenario: reindex reports what changed since the last build
- **GIVEN** a vault whose index is already built and fresh
- **WHEN** `reindex()` is called with no changes made to the vault
  since the last build
- **THEN** the returned `IndexReport` reports nothing added, changed,
  or deleted

#### Scenario: force=True re-embeds everything
- **GIVEN** a vault with a built, fresh index
- **WHEN** `reindex(force=True)` is called
- **THEN** the returned `IndexReport` reflects every row being
  re-embedded, not only rows whose content changed

### Requirement: a write followed by search in the same process needs no reopened index
`append_note`, `set_status`, `add_document`, and `create_vacancy` SHALL
each leave the index in a state where a subsequent `search` call, in
the same process, sees the write's effect without the caller reopening
or reconnecting to the index.

#### Scenario: Search sees a write without a new index connection
- **WHEN** a write function is called and returns successfully, and a
  `search` call is made immediately afterward using the same process's
  existing index handle
- **THEN** the search reflects the write's effect
