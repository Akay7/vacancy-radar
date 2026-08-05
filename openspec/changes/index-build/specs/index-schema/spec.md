## ADDED Requirements

### Requirement: The index table has one row per indexable unit, never a sub-document chunk
The LanceDB table SHALL hold exactly one row per indexable document
(every `Document`, plus one row per `Vacancy`) and SHALL NOT split any
single document's or vacancy's text into multiple rows.

#### Scenario: row count matches indexable document and vacancy counts
- **GIVEN** a `VaultSnapshot` with a known number of documents and
  vacancies
- **WHEN** the table is built from that snapshot
- **THEN** the table's row count equals the number of documents plus
  the number of vacancies

### Requirement: The table schema includes denormalized vacancy fields
Every document row SHALL carry its parent vacancy's `company_slug`,
`company`, `role`, and `status` denormalized onto the row itself,
alongside `doc_id`, `vacancy_id`, `kind`, `title`, `path`, `date`,
`found_date`, `applied_date`, `last_activity`, `tags`, `text`,
`content_hash`, and `vector`.

#### Scenario: a document row's denormalized fields match its parent vacancy
- **GIVEN** a document belonging to a vacancy with a known
  `company_slug`, `company`, `role`, and `status`
- **WHEN** the table is built and that document's row is read back
- **THEN** the row's `company_slug`, `company`, `role`, and `status`
  equal the parent vacancy's values

### Requirement: Vector dimensionality is derived from the configured embedding model
Table creation SHALL take the vector dimensionality as a parameter
derived from the currently configured embedding model, never a
hardcoded constant.

#### Scenario: table creation accepts the model's reported dimension
- **GIVEN** an embedding model reporting a known vector dimension
- **WHEN** the table is created for that dimension
- **THEN** the table's `vector` column has that exact dimensionality
