# reindexing Specification

## Purpose
TBD - created by openspec-sync-specs during change cli-write. Update Purpose after archive.

## Requirements

### Requirement: reindex wraps stage 3's incremental build over a fresh snapshot
`reindex(force=False, extract_sidecars=False)` SHALL re-read the vault
into a fresh `VaultSnapshot` and run stage 3's `build_index` against
it, passing `force` and `extract_sidecars` through unchanged, returning
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

#### Scenario: extract_sidecars=True extracts an eligible PDF's sidecar
- **GIVEN** a vault with a valid, text-bearing PDF filed under a
  vacancy's `documents/` directory, and no existing sidecar for it
- **WHEN** `reindex(extract_sidecars=True)` is called
- **THEN** a `.pdf.md` sidecar now exists for that PDF, containing its
  extracted text

#### Scenario: extract_sidecars=False (the default) extracts nothing
- **GIVEN** the same vault as above, with no existing sidecar for its
  PDF
- **WHEN** `reindex()` is called with no `extract_sidecars` argument
- **THEN** no sidecar is created for that PDF - identical to this
  function's behavior before `extract_sidecars` existed

#### Scenario: extract_sidecars=True against a malformed PDF returns a warning, not a crash
- **GIVEN** a vault with a malformed (unparseable) `.pdf` file under a
  vacancy's `documents/` directory
- **WHEN** `reindex(extract_sidecars=True)` is called
- **THEN** the call returns without raising, the resulting sidecar's
  body is empty (extraction failed but was handled, per
  `extract_to_sidecar`'s own contract), and the returned
  `IndexReport`'s `warnings` includes an entry naming that file

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
