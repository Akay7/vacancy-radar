# vault-reader Specification

## Purpose
TBD - created by openspec-sync-specs during change vault-reader. Update Purpose after archive.

## Requirements

### Requirement: read_vault produces a snapshot with correct counts and attribution
`read_vault(path)` SHALL traverse the vault tree and return a
`VaultSnapshot` whose `vacancies`, `documents`, and `companies` reflect
every parseable file found, with vacancies keyed by the `id` in their
frontmatter (not their directory name) and documents attributed to the
vacancy whose `documents/` directory contains them.

#### Scenario: reading the fixture vault yields the expected counts
- **GIVEN** the committed `tests/fixtures/vault/` tree
- **WHEN** `read_vault` is called on it
- **THEN** the returned snapshot's vacancy, document, and company
  counts match the counts obtained by independently walking the
  fixture tree

#### Scenario: vacancy id matches frontmatter, not directory name
- **GIVEN** a vacancy directory in the fixture vault whose name differs
  from the `id` field in its `vacancy.md` frontmatter
- **WHEN** `read_vault` is called
- **THEN** the vacancy appears in the snapshot keyed by its frontmatter
  `id`, not by its directory name

#### Scenario: documents are attributed to the containing vacancy
- **GIVEN** a vacancy directory containing a `documents/` directory
  with one or more document files
- **WHEN** `read_vault` is called
- **THEN** each document in the snapshot has `vacancy_id` equal to the
  id of the vacancy whose `documents/` directory contains it

### Requirement: A company with no vacancies still parses
`read_vault` SHALL parse a company directory containing `_company.md`
but no vacancy subdirectories into a `Company` in the snapshot, and
`vacancies_for` that company's slug SHALL return an empty list.

#### Scenario: a company directory with _company.md but no vacancies parses
- **GIVEN** a company directory containing `_company.md` and no vacancy
  subdirectories
- **WHEN** `read_vault` is called
- **THEN** the snapshot's `companies` includes a `Company` for that
  slug
- **THEN** `snapshot.vacancies_for(slug)` returns an empty list

### Requirement: Non-markdown documents are registered by path, not parsed
`read_vault` SHALL register a non-markdown file (no `.md` extension)
inside a vacancy's `documents/` directory as a `Document` identified by
its path, without attempting to parse it as frontmatter. A `.md` file
whose parsed frontmatter contains an `extracted_from` key is a sidecar,
not a `Document`: `read_vault` SHALL exclude it from `documents`
entirely (it contributes no row of its own — the source file it
shadows is already registered via this same non-markdown path) and
SHALL NOT attempt to validate it against the `Document` schema.

#### Scenario: a non-markdown file in documents/ is indexed by path
- **GIVEN** a vacancy's `documents/` directory containing a
  non-markdown file (e.g. a `.pdf`)
- **WHEN** `read_vault` is called
- **THEN** the snapshot includes a `Document` for that file
- **THEN** no attempt to parse YAML frontmatter from that file causes a
  warning or error

#### Scenario: a well-formed sidecar is excluded from documents without a warning
- **GIVEN** a vacancy's `documents/` directory containing a source file
  `spec.pdf` and a sidecar `spec.pdf.md` whose frontmatter has
  `extracted_from: spec.pdf`
- **WHEN** `read_vault` is called
- **THEN** the snapshot's `documents` includes exactly one document for
  that pair — the one keyed by `spec.pdf`'s registration — and none
  for `spec.pdf.md`
- **THEN** no warning is produced for `spec.pdf.md`

#### Scenario: a sidecar is never validated against the Document schema
- **GIVEN** a sidecar file whose frontmatter (`extracted_from`,
  `source_hash`, `extractor`, `extracted_at`, `manually_corrected`)
  has none of the fields a `Document` requires (`id`, `vacancy_id`,
  `kind`, `title`, `date`)
- **WHEN** `read_vault` is called
- **THEN** no `invalid_document` warning is produced for that file

### Requirement: Traversal skips dotfiles and internal directories
Traversal SHALL skip dotfiles, `.git/`, `.index/`, and the
`.vacancy-radar/` marker directory — none of their contents SHALL
appear in the snapshot or produce warnings.

#### Scenario: dotfiles, .git/, .index/, and the marker directory are skipped
- **GIVEN** a vault containing a dotfile at its root, a `.git/`
  directory, a `.index/` directory, and the `.vacancy-radar/` marker
  directory, each with content that would fail to parse as a vacancy
  or document if read
- **WHEN** `read_vault` is called
- **THEN** none of that content appears in the snapshot
- **THEN** none of that content produces a warning

### Requirement: A malformed file never aborts the read
`read_vault` SHALL collect every file-level failure — unparseable
YAML, an unknown status, an unreadable file, a duplicate vacancy id, or
a document directory with no `vacancy.md` — as a `VaultWarning` on the
snapshot rather than raising, and SHALL NOT let any such failure
prevent every other, well-formed file from loading successfully.

#### Scenario: unparseable YAML in vacancy.md produces a warning and is excluded
- **GIVEN** a vault containing one `vacancy.md` with unparseable YAML
  frontmatter, alongside other well-formed vacancies
- **WHEN** `read_vault` is called
- **THEN** a warning naming that file is present in
  `snapshot.warnings`
- **THEN** that vacancy is absent from `snapshot.vacancies`
- **THEN** every other, well-formed vacancy is present in
  `snapshot.vacancies`

#### Scenario: an unknown status produces a warning and is excluded
- **GIVEN** a vault containing one `vacancy.md` whose `status` field is
  not one of the eight defined `Status` values, alongside other
  well-formed vacancies
- **WHEN** `read_vault` is called
- **THEN** a warning naming that file is present in
  `snapshot.warnings`
- **THEN** that vacancy is absent from `snapshot.vacancies`
- **THEN** every other, well-formed vacancy is present in
  `snapshot.vacancies`

#### Scenario: an unreadable file produces a warning, not a crash
- **GIVEN** a vault containing one file whose permissions make it
  unreadable by the current process
- **WHEN** `read_vault` is called
- **THEN** `read_vault` returns a snapshot rather than raising
- **THEN** a warning naming that file is present in
  `snapshot.warnings`

#### Scenario: duplicate vacancy ids produce a warning and one survivor
- **GIVEN** two `vacancy.md` files in different directories whose
  frontmatter `id` fields are identical
- **WHEN** `read_vault` is called
- **THEN** exactly one vacancy with that id is present in
  `snapshot.vacancies`
- **THEN** which of the two paths survives is deterministic (repeated
  reads of the same vault state pick the same survivor)
- **THEN** a warning naming both paths is present in
  `snapshot.warnings`

#### Scenario: a documents/ directory with no vacancy.md produces an orphan warning
- **GIVEN** a vacancy directory containing a `documents/` directory but
  no `vacancy.md`
- **WHEN** `read_vault` is called
- **THEN** a warning naming that directory is present in
  `snapshot.warnings`
- **THEN** no documents from that directory are attributed to any
  vacancy in the snapshot

### Requirement: A company referencing no _company.md produces a warning
`read_vault` SHALL still load, as a vacancy, one whose `company_slug`
has no corresponding company directory with `_company.md`, and SHALL
produce a warning naming the missing company.

#### Scenario: a vacancy referencing a company with no _company.md produces a warning
- **GIVEN** a vacancy directory under a company slug whose directory
  has no `_company.md`
- **WHEN** `read_vault` is called
- **THEN** the vacancy is present in `snapshot.vacancies`
- **THEN** a warning naming the missing company is present in
  `snapshot.warnings`

### Requirement: Reading is deterministic and hashes each file once
Reading the same, unchanged vault twice SHALL produce identical hash
maps. Changing exactly one file's content between two reads SHALL
change exactly that file's entry in the hash map. Each file SHALL be
hashed exactly once per `read_vault` call.

#### Scenario: reading twice with no change produces identical hash maps
- **GIVEN** a vault that is not modified between two reads
- **WHEN** `read_vault` is called twice on it
- **THEN** the two resulting `hashes` mappings are identical, key for
  key and value for value

#### Scenario: editing one file changes exactly one hash map entry
- **GIVEN** a vault that has been read once, producing a hash map
- **WHEN** one file's content is changed and the vault is read again
- **THEN** the new hash map differs from the old one at exactly the
  entry for the changed file

### Requirement: last_activity falls back through documents, applied_date, found_date
`snapshot.last_activity(vacancy_id)` SHALL return the most recent
document date among that vacancy's documents when any exist. When no
documents exist, it SHALL fall back to `applied_date`. When neither
documents nor `applied_date` exist (a `found`-status vacancy with no
documents), it SHALL fall back to `found_date`.

#### Scenario: last_activity returns the most recent document date
- **GIVEN** a vacancy with two or more documents having distinct dates
- **WHEN** `last_activity` is called with that vacancy's id
- **THEN** it returns the most recent of those document dates

#### Scenario: last_activity falls back to applied_date with no documents
- **GIVEN** a vacancy with no documents and a non-null `applied_date`
- **WHEN** `last_activity` is called with that vacancy's id
- **THEN** it returns `applied_date`

#### Scenario: last_activity falls back to found_date for a found vacancy
- **GIVEN** a `found`-status vacancy with no documents (and therefore
  no `applied_date`)
- **WHEN** `last_activity` is called with that vacancy's id
- **THEN** it returns `found_date`

### Requirement: documents_for returns date-ascending, stably-ordered documents
`snapshot.documents_for(vacancy_id)` SHALL return that vacancy's
documents ordered by date ascending, with ties between same-date
documents broken stably (matching their relative order as read from
disk).

#### Scenario: documents_for returns documents in ascending date order
- **GIVEN** a vacancy with documents of distinct dates in no particular
  disk order
- **WHEN** `documents_for` is called with that vacancy's id
- **THEN** the returned list is ordered by date ascending

#### Scenario: same-day documents keep a stable relative order
- **GIVEN** a vacancy with two or more documents sharing the same date
- **WHEN** `documents_for` is called with that vacancy's id, across
  repeated calls on the same snapshot
- **THEN** those same-date documents appear in the same relative order
  every time

### Requirement: VaultSnapshot is immutable
`VaultSnapshot` SHALL be read-only: no public API on the snapshot or on
the collections it exposes (`vacancies`, `documents`, `companies`,
`hashes`) SHALL allow a caller to mutate its contents in place.

#### Scenario: mutating a snapshot's exposed collection is rejected
- **GIVEN** a `VaultSnapshot` returned by `read_vault`
- **WHEN** an attempt is made to assign into or otherwise mutate one of
  its exposed collections (e.g. `snapshot.vacancies[some_id] = ...`)
- **THEN** the attempt raises an error rather than silently succeeding

### Requirement: Reading a large vault completes quickly and hashes each file once
Reading a generated vault of roughly 700 vacancies SHALL complete
within a few seconds, and each file in that vault SHALL be hashed
exactly once during the read.

#### Scenario: a 700-vacancy vault reads within a few seconds
- **GIVEN** a generated vault of roughly 700 vacancies (via the scale
  override to `generate_vault`)
- **WHEN** `read_vault` is called and timed
- **THEN** it completes within a few seconds

#### Scenario: each file is hashed exactly once
- **GIVEN** a generated vault of roughly 700 vacancies
- **WHEN** `read_vault` is called with hashing instrumented to count
  calls per file
- **THEN** every file is hashed exactly once

### Requirement: An orphaned sidecar produces a warning
`read_vault` SHALL produce a warning naming a sidecar (a `.md` file
whose frontmatter contains `extracted_from`) whose named source file
does not exist in the same directory, and SHALL exclude it from
`documents`.

#### Scenario: a sidecar with no matching source produces an orphan warning
- **GIVEN** a `documents/` directory containing a sidecar
  `spec.pdf.md` with `extracted_from: spec.pdf`, and no `spec.pdf` file
  present
- **WHEN** `read_vault` is called
- **THEN** a warning naming `spec.pdf.md` is present in
  `snapshot.warnings`
- **THEN** `spec.pdf.md` is absent from `snapshot.documents`

### Requirement: A mismatched sidecar produces a warning
`read_vault` SHALL produce a warning naming a sidecar whose
`extracted_from` value disagrees with its own filename (the sidecar's
filename minus its trailing `.md` does not equal `extracted_from`),
and SHALL exclude it from `documents`.

#### Scenario: a sidecar whose extracted_from disagrees with its filename produces a warning
- **GIVEN** a `documents/` directory containing a file named
  `spec.pdf.md` whose frontmatter has `extracted_from: other.pdf`
- **WHEN** `read_vault` is called
- **THEN** a warning naming `spec.pdf.md` is present in
  `snapshot.warnings`
- **THEN** `spec.pdf.md` is absent from `snapshot.documents`

### Requirement: Independent sidecars for same-stem sources don't shadow each other
`read_vault` SHALL match two sources in the same directory whose names
differ only by extension (e.g. `notes.pdf` and `notes.docx`) each only
to the sidecar whose `extracted_from` names it exactly.

#### Scenario: notes.pdf and notes.docx each keep their own sidecar
- **GIVEN** a `documents/` directory containing `notes.pdf`,
  `notes.pdf.md` (`extracted_from: notes.pdf`), `notes.docx`, and
  `notes.docx.md` (`extracted_from: notes.docx`)
- **WHEN** `read_vault` is called
- **THEN** both `notes.pdf` and `notes.docx` are registered as
  independent `Document`s
- **THEN** neither `notes.pdf.md` nor `notes.docx.md` is registered as
  a `Document`, and neither produces a warning

### Requirement: VaultSnapshot exposes each vacancy's and document's file path
`VaultSnapshot` SHALL expose `vacancy_paths` (vacancy id to its
`vacancy.md` path) and `document_paths` (document id to its file path),
alongside `vacancies` and `documents`, so a caller can locate a row's
underlying file without re-deriving it from layout conventions. Both
SHALL be immutable, matching every other exposed collection on the
snapshot.

#### Scenario: document_paths maps a document id to its actual file path
- **GIVEN** a document with a known id inside a vacancy's `documents/`
  directory
- **WHEN** `read_vault` is called
- **THEN** `snapshot.document_paths` maps that document's id to its
  actual file path

#### Scenario: vacancy_paths maps a vacancy id to its vacancy.md path
- **GIVEN** a vacancy whose frontmatter `id` differs from its directory
  name
- **WHEN** `read_vault` is called
- **THEN** `snapshot.vacancy_paths` maps that vacancy's frontmatter id
  to its actual `vacancy.md` path

#### Scenario: mutating vacancy_paths or document_paths is rejected
- **GIVEN** a `VaultSnapshot` returned by `read_vault`
- **WHEN** an attempt is made to assign into `snapshot.vacancy_paths` or
  `snapshot.document_paths`
- **THEN** the attempt raises an error rather than silently succeeding
