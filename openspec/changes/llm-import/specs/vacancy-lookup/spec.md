## ADDED Requirements

### Requirement: find_existing matches vacancies by resolved company
`find_existing(company, source_url)` SHALL, when `company` resolves to
exactly one company via `resolve`'s own tiers (exact slug, exact
case-insensitive name, unique fuzzy name), return every vacancy under
that company as a `VacancySummary` row.

#### Scenario: A company that exists returns its vacancies
- **GIVEN** a vault company with two vacancies
- **WHEN** `find_existing` is called with that company's exact display
  name and a `source_url` matching neither vacancy
- **THEN** the returned list contains both vacancies' summaries

### Requirement: find_existing returns an empty list when neither company nor source_url matches
`find_existing(company, source_url)` SHALL return an empty list,
without raising, when `company` does not resolve to any company at any
tier and `source_url` matches no vacancy in the vault.

#### Scenario: A company that does not exist, with no matching source_url, returns empty
- **GIVEN** a vault with no company matching a given name
- **WHEN** `find_existing` is called with that name and a `source_url`
  not present on any vacancy
- **THEN** the returned list is empty and no exception is raised

### Requirement: find_existing never raises on an ambiguous or unresolved company
`find_existing(company, source_url)` SHALL, when `company` matches zero
or more than one company at `resolve`'s matching tiers, treat the
company argument as contributing no rows rather than raising
`EntityNotFoundError` or `AmbiguousEntityError` — `source_url` matching
SHALL still run independently.

#### Scenario: An ambiguous company argument does not raise
- **GIVEN** a vault with two companies whose display names both
  fuzzy-match a given query
- **WHEN** `find_existing` is called with that query and a `source_url`
  matching one of those companies' vacancies
- **THEN** the call returns without raising, and the list contains the
  vacancy whose `source_url` matched

### Requirement: find_existing matches on source_url independent of company-name spelling
`find_existing(company, source_url)` SHALL include a vacancy whose
`source_url` equals the given `source_url` exactly, regardless of
whether the given `company` argument resolves to that vacancy's own
company.

#### Scenario: A differently-spelled company argument still matches by source_url
- **GIVEN** a vacancy filed under a company display name, with a known
  `source_url`
- **WHEN** `find_existing` is called with a `company` spelling that does
  not resolve to that company (via any `resolve` tier) but with that
  vacancy's exact `source_url`
- **THEN** the returned list contains that vacancy's summary

### Requirement: find_existing returns each matching vacancy once
`find_existing(company, source_url)` SHALL, when a vacancy matches both
the company tier and the `source_url` tier, include it exactly once in
the returned list.

#### Scenario: A vacancy matching both criteria is not duplicated
- **GIVEN** a vacancy belonging to a company that resolves from the
  given `company` argument, whose `source_url` also equals the given
  `source_url`
- **WHEN** `find_existing` is called with both arguments
- **THEN** that vacancy's summary appears exactly once in the returned
  list
