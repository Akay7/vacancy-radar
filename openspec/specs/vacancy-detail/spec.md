# vacancy-detail Specification

## Purpose
TBD - created by openspec-sync-specs during change retrieval. Update Purpose after archive.

## Requirements

### Requirement: get_vacancy lists documents date-ascending with titles and paths
`get_vacancy(id_or_query)` SHALL return the vacancy's documents sorted
by `date` ascending, each with its `title` and vault-relative path.

#### Scenario: Documents are listed date-ascending with titles and paths
- **WHEN** `get_vacancy` is called for a vacancy with several documents
  of differing dates
- **THEN** the returned `VacancyDetail`'s documents appear ordered by
  date ascending, each carrying a title and a path

### Requirement: get_vacancy returns stage_note verbatim
`get_vacancy(id_or_query)` SHALL return the vacancy's `stage_note`
field exactly as stored, with no transformation.

#### Scenario: stage_note is returned verbatim
- **WHEN** `get_vacancy` is called for a vacancy with a `stage_note`
- **THEN** the returned `VacancyDetail.stage_note` equals the
  vacancy's stored `stage_note` exactly

### Requirement: a vacancy with zero documents returns successfully
`get_vacancy(id_or_query)` SHALL succeed for a vacancy with no
documents, returning an empty documents list rather than raising.

#### Scenario: A vacancy with zero documents returns successfully
- **WHEN** `get_vacancy` is called for a vacancy with no documents
- **THEN** the returned `VacancyDetail` has an empty documents list and
  no exception is raised

### Requirement: document bodies are absent from vacancy detail
`get_vacancy`'s document list SHALL contain paths, titles, kinds, and
dates only — never document text.

#### Scenario: Bodies are absent from the response
- **WHEN** `get_vacancy` is called for a vacancy with documents
- **THEN** no document body appears anywhere in the returned
  `VacancyDetail`
