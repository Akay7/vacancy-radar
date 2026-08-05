## MODIFIED Requirements

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

## ADDED Requirements

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
