## MODIFIED Requirements

### Requirement: write commands resolve a vacancy by id, company name, or fuzzy match
`note`, `status set`, `edit`, and `add` SHALL accept a vacancy argument
that resolves via `core.resolve_vacancy`: exact vacancy id, exact
company slug, exact company name, or unambiguous fuzzy company name,
with a company-tier match narrowed to that company's single vacancy.
A company holding more than one vacancy, or none, SHALL exit non-zero
without writing.

#### Scenario: A command accepts a vacancy by its exact id
- **WHEN** a write command is given an existing vacancy's exact id
- **THEN** it operates on that vacancy

#### Scenario: A command accepts a vacancy by an unambiguous fuzzy company match
- **WHEN** a write command is given a query that fuzzy-matches exactly
  one company with exactly one vacancy eligible for the operation
- **THEN** it operates on that vacancy

#### Scenario: A command accepts a vacancy by its company's exact display name
- **GIVEN** a company with exactly one vacancy
- **WHEN** a write command is given that company's display name
- **THEN** it operates on that vacancy and exits 0

#### Scenario: A company with several vacancies exits non-zero naming them
- **GIVEN** a company with two vacancies
- **WHEN** a write command is given that company's name
- **THEN** the command exits non-zero, its output names both vacancy
  ids, and no file in the vault is modified

#### Scenario: A company with no vacancies exits non-zero
- **GIVEN** a company directory with no vacancies
- **WHEN** a write command is given that company's name
- **THEN** the command exits non-zero and no file in the vault is
  modified

### Requirement: an ambiguous vacancy match writes nothing and exits non-zero
`note`, `status set`, `edit`, and `add` SHALL, when the vacancy
argument cannot be narrowed to exactly one vacancy — because
`core.resolve` returned more than one company candidate, or because the
resolved company holds more than one vacancy — print what it matched
and exit non-zero without performing any write.

#### Scenario: An ambiguous query blocks the write
- **GIVEN** a query that resolves to more than one vacancy or company
- **WHEN** `note`, `status set`, `edit`, or `add` is run with that
  query
- **THEN** the command exits non-zero, prints the candidates, and no
  file in the vault is modified
