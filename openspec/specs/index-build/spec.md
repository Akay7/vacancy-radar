# index-build Specification

## Purpose
TBD - created by openspec-sync-specs during change index-build. Update Purpose after archive.

## Requirements

### Requirement: A shadowed source's row takes its text from the sidecar
`build_index` SHALL, for a `Document` whose source file has a matching
sidecar (per the reader's sidecar recognition), use the sidecar's body
as that row's `text`.

#### Scenario: a source with a sidecar embeds the sidecar's text
- **GIVEN** a source `spec.pdf` with a matching sidecar `spec.pdf.md`
  containing extracted text
- **WHEN** `build_index` is called
- **THEN** the row for `spec.pdf` has `text` equal to the sidecar's
  body

### Requirement: A source with no sidecar text indexes by filename
`build_index` SHALL, for a `Document` whose source has no sidecar (not
attempted, or attempted and empty), fall back to the document's title
and filename as that row's `text`, rather than omitting the row.

#### Scenario: a source with no sidecar and no extractable text indexes by filename
- **GIVEN** a source document with no sidecar present
- **WHEN** `build_index` is called
- **THEN** a row for that source exists in the table
- **THEN** its `text` is derived from its title and filename, not empty

### Requirement: content_hash diffing uses the source file's hash, not the sidecar's
`build_index` SHALL diff a document row's staleness against its source
file's content hash (from the snapshot's hash map), never the
sidecar's own hash.

#### Scenario: a source file's hash change is what triggers re-embedding
- **GIVEN** a document row already indexed, and a snapshot in which
  only the source file's content changed (its hash differs from the
  row's stored `content_hash`)
- **WHEN** `build_index` is called with the new snapshot
- **THEN** that row is re-embedded

### Requirement: Building from empty produces one row per indexable unit
`build_index`, run against an index with no existing table, SHALL
produce exactly one row per document plus one row per vacancy in the
snapshot.

#### Scenario: building from empty over the fixture vault produces the expected row count
- **GIVEN** an index path with no existing table, and the committed
  fixture vault's snapshot
- **WHEN** `build_index` is called
- **THEN** the resulting table's row count equals the snapshot's
  document count plus its vacancy count

#### Scenario: every row's content_hash matches its snapshot hash
- **GIVEN** a freshly built table
- **WHEN** each row's `content_hash` is compared to the snapshot's
  hash for that row's `path`
- **THEN** every row's `content_hash` matches

### Requirement: Building twice with no change re-embeds nothing
Calling `build_index` a second time against an unmodified vault SHALL
report zero added, zero changed, and zero deleted, with every row
counted as unchanged.

#### Scenario: a no-change rebuild embeds zero documents
- **GIVEN** a table already built from a snapshot
- **WHEN** `build_index` is called again with an unmodified snapshot of
  the same vault
- **THEN** the returned `IndexReport` has `added == 0`, `changed == 0`,
  and `deleted == 0`

### Requirement: Editing a document's body re-embeds exactly that document
Changing one document's text content between builds SHALL cause
exactly that document's row to be re-embedded, with every other row
unchanged.

#### Scenario: editing one document re-embeds exactly one row
- **GIVEN** a table already built, and one document's body edited (its
  content hash changes) before the next `build_index` call
- **WHEN** `build_index` is called again
- **THEN** the returned `IndexReport` has `changed == 1`
- **THEN** the row for the edited document has a new `content_hash`
  and `vector`
- **THEN** every other row's `content_hash` and `vector` are unchanged

### Requirement: A frontmatter-only vacancy edit re-embeds only the vacancy row
`build_index` SHALL re-embed only a vacancy's own row when just its
frontmatter changes (its `vacancy.md` hash changes, no sibling
document's content changes), and SHALL update its documents'
denormalized columns without re-embedding those documents.

#### Scenario: a status change re-embeds the vacancy row and refreshes sibling documents' status column
- **GIVEN** a table already built, and a vacancy's `status` changed
  (no document content changed) before the next `build_index` call
- **WHEN** `build_index` is called again
- **THEN** the vacancy's own row is re-embedded (new `content_hash` and
  `vector`)
- **THEN** every sibling document row's `content_hash` and `vector` are
  unchanged
- **THEN** every sibling document row's denormalized `status` column
  equals the vacancy's new status

### Requirement: Adding a document adds exactly one row
A new document appearing in the vault between builds SHALL add exactly
one new row on the next `build_index` call.

#### Scenario: adding one document adds one row
- **GIVEN** a table already built, and one new document file added to
  the vault before the next `build_index` call
- **WHEN** `build_index` is called again
- **THEN** the returned `IndexReport` has `added == 1`
- **THEN** the table's row count increases by exactly one

### Requirement: Deleting a source removes exactly its row
A source file removed from the vault between builds SHALL cause its
row to be deleted on the next `build_index` call.

#### Scenario: deleting one source file removes exactly one row
- **GIVEN** a table already built, and one document's source file
  deleted from the vault before the next `build_index` call
- **WHEN** `build_index` is called again with the updated snapshot
- **THEN** the returned `IndexReport` has `deleted == 1`
- **THEN** the table no longer contains a row for that document's
  `doc_id`

### Requirement: force=True re-embeds everything
`build_index` called with `force=True` SHALL re-embed every row
regardless of whether its content hash changed.

#### Scenario: force=True re-embeds an unmodified vault's rows
- **GIVEN** a table already built from an unmodified vault
- **WHEN** `build_index` is called again with `force=True`
- **THEN** the returned `IndexReport`'s `changed` count equals the
  total row count, and `unchanged == 0`

### Requirement: Deleting and rebuilding the index reproduces equivalent state
`build_index` SHALL reproduce the same row count and the same set of
`doc_id`s as before, when the entire index directory is deleted and a
build is run again against an unchanged vault.

#### Scenario: delete .index/ and rebuild reproduces row count and doc_ids
- **GIVEN** a table built from the fixture vault, with its row count
  and full set of `doc_id`s recorded
- **WHEN** the index directory is deleted entirely and `build_index` is
  called again with the same snapshot
- **THEN** the rebuilt table's row count equals the recorded count
- **THEN** the rebuilt table's set of `doc_id`s equals the recorded set

### Requirement: The FTS index exists after a build and survives incremental changes
`build_index` SHALL create the full-text index if absent, and SHALL
refresh it (via `optimize()`) so rows written or changed during the
build are searchable immediately afterward, without duplicating or
corrupting entries on repeated builds.

#### Scenario: the FTS index exists after the first build
- **GIVEN** an index path with no existing table
- **WHEN** `build_index` is called
- **THEN** the table has a full-text index on its `text` column

#### Scenario: newly added documents are searchable after a build
- **GIVEN** a table already built, and one new document added before
  the next `build_index` call
- **WHEN** `build_index` is called again
- **THEN** an FTS query for a term unique to the new document's text
  returns that document's row

#### Scenario: rebuilding does not duplicate FTS entries
- **GIVEN** a table built, then rebuilt twice more with no vault
  changes
- **WHEN** an FTS query is run for a term known to match exactly one
  row
- **THEN** exactly one row is returned, not more

### Requirement: A snapshot's own warnings carry into the IndexReport
`build_index` SHALL include every warning already present on the input
`VaultSnapshot` in the returned `IndexReport`'s warnings, alongside any
warnings raised during the build itself.

#### Scenario: vault warnings appear in the IndexReport
- **GIVEN** a `VaultSnapshot` with one or more warnings already present
- **WHEN** `build_index` is called with that snapshot
- **THEN** the returned `IndexReport`'s warnings include every warning
  from the snapshot

### Requirement: A vanished source file is skipped with a warning, not a crash
`build_index` SHALL, for a document whose source file existed in the
snapshot but no longer exists on disk when the build reads it, skip
that document (no row written or updated) and report a warning, rather
than raising.

#### Scenario: a file that disappears between snapshot and build produces a warning
- **GIVEN** a snapshot referencing a document whose source file is
  deleted after the snapshot was taken but before `build_index` reads
  it
- **WHEN** `build_index` is called with that snapshot
- **THEN** `build_index` completes without raising
- **THEN** the returned `IndexReport` has a warning naming that
  document
- **THEN** `IndexReport.skipped` is at least 1

### Requirement: A large vault builds within a practical time budget
`build_index` SHALL complete within a few minutes on CPU when run from
empty over a generated ~700-vacancy (~3000-document) vault, and a
subsequent no-change rebuild over the same vault SHALL complete within
seconds.

#### Scenario: a full build over a large vault completes within minutes
- **GIVEN** a generated vault of roughly 700 vacancies (via the stage 2
  scale override)
- **WHEN** `build_index` is called against it from empty, timed
- **THEN** it completes within a few minutes

#### Scenario: a no-change rebuild over the same large vault completes within seconds
- **GIVEN** the large vault's index already built once
- **WHEN** `build_index` is called again with an unmodified snapshot,
  timed
- **THEN** it completes within seconds

### Requirement: Table creation stamps the active build's embedding model into schema metadata
`build_index` SHALL, whenever it creates a table (a fresh build, or a
dimension-mismatch recreate), stamp the `model_name` it was called with
into the new table's schema metadata. `build_index` SHALL NOT alter an
existing, reused table's recorded metadata.

#### Scenario: a fresh build records the model it was called with
- **GIVEN** an index path with no existing table
- **WHEN** `build_index` is called with a given `model_name`
- **THEN** the resulting table's schema metadata records that
  `model_name`

#### Scenario: a dimension-driven recreate records the new model
- **GIVEN** an existing table built for one embedding model, and
  `build_index` called again with a different `model_name` whose vector
  dimension differs from the existing table's
- **WHEN** `build_index` runs (triggering the existing dimension-mismatch
  recreate path)
- **THEN** the recreated table's schema metadata records the new
  `model_name`, not the old one

#### Scenario: an incremental build with no dimension change leaves recorded metadata untouched
- **GIVEN** an existing table already recording a `model_name`
- **WHEN** `build_index` is called again with the same `model_name` (no
  table recreation)
- **THEN** the table's schema metadata still records the original
  `model_name`, unchanged
</content>
