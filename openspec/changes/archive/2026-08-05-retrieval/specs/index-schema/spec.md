## ADDED Requirements

### Requirement: The table schema records the embedding model that built it
The table's Arrow schema metadata SHALL, once the table has been
created, carry the name of the embedding model used to build its
vectors, retrievable without out-of-band bookkeeping and surviving a
`connect()`/`open_table()` round-trip.

#### Scenario: a freshly created table's schema metadata records the model name
- **GIVEN** a table created for a known embedding model name
- **WHEN** the table is reopened via `connect()`/`open_table()` in a new
  connection
- **THEN** its schema metadata contains that exact model name
