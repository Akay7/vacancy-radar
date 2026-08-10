## ADDED Requirements

### Requirement: create_vacancy accepts an optional source_url
`create_vacancy` SHALL accept `source_url` as an optional parameter
(`str | None`, defaulting to `None`), forwarded to the created
`Vacancy` unchanged. No new validation is added beyond what `Vacancy`'s
existing field validator already enforces when a value is given (must
be `http` or `https`).

#### Scenario: create_vacancy without source_url creates a vacancy with none
- **WHEN** `create_vacancy` is called with no `source_url` argument
- **THEN** the created vacancy's `source_url` is absent from its
  frontmatter

#### Scenario: create_vacancy with a valid source_url stores it unchanged
- **WHEN** `create_vacancy` is called with a valid `http`/`https`
  `source_url`
- **THEN** the created vacancy's frontmatter carries that `source_url`
  unchanged

#### Scenario: create_vacancy with an invalid-scheme source_url still raises
- **WHEN** `create_vacancy` is called with a `source_url` whose scheme
  is not `http` or `https`
- **THEN** `InvalidVacancyDataError` is raised and no company directory
  or vacancy file is created
