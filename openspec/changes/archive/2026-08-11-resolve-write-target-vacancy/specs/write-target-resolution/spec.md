## ADDED Requirements

### Requirement: resolve_vacancy returns a single vacancy id for a query
`core.resolve_vacancy(query, vault=None)` SHALL return exactly one
vacancy id for a query that identifies one vacancy, using `resolve`'s
own tier order — exact vacancy id, exact company slug, exact
case-insensitive company name, unambiguous fuzzy company name — and
narrowing a company-tier match to that company's vacancies.

#### Scenario: an exact vacancy id resolves to itself
- **WHEN** `resolve_vacancy` is called with an existing vacancy's exact
  id
- **THEN** it returns that id

#### Scenario: an exact company slug resolves to that company's one vacancy
- **GIVEN** a company with exactly one vacancy
- **WHEN** `resolve_vacancy` is called with that company's exact slug
- **THEN** it returns that vacancy's id

#### Scenario: a company display name resolves to that company's one vacancy
- **GIVEN** a company with exactly one vacancy
- **WHEN** `resolve_vacancy` is called with that company's display name,
  in any case
- **THEN** it returns that vacancy's id

#### Scenario: an unambiguous fuzzy company name resolves to that company's one vacancy
- **GIVEN** a company with exactly one vacancy, and no other company
  whose name is a close match
- **WHEN** `resolve_vacancy` is called with a partial form of that
  company's name
- **THEN** it returns that vacancy's id

#### Scenario: the vacancy-id tier still short-circuits the company tiers
- **GIVEN** a vacancy whose id is also a close fuzzy match for some
  company's display name
- **WHEN** `resolve_vacancy` is called with that exact id
- **THEN** it returns that id, without consulting any company tier

### Requirement: a company holding several vacancies raises AmbiguousVacancyError
`resolve_vacancy` SHALL raise `AmbiguousVacancyError` when the query
resolves to a company with more than one vacancy. The error SHALL name
the company and every candidate vacancy id, and SHALL NOT pick one.

#### Scenario: a two-vacancy company raises, naming both ids
- **GIVEN** a company with two vacancies
- **WHEN** `resolve_vacancy` is called with that company's name
- **THEN** `AmbiguousVacancyError` is raised and its message names both
  vacancy ids

#### Scenario: the raised error carries the candidate ids as data
- **GIVEN** a company with two vacancies
- **WHEN** `resolve_vacancy` is called with that company's name
- **THEN** the raised error exposes the candidate vacancy ids as an
  attribute, not only inside its message text

### Requirement: a company with no vacancies raises EntityNotFoundError
`resolve_vacancy` SHALL raise `EntityNotFoundError` when the query
resolves to a company that holds no vacancies.

#### Scenario: an empty company raises rather than returning nothing
- **GIVEN** a company directory with a `_company.md` and no vacancies
- **WHEN** `resolve_vacancy` is called with that company's name
- **THEN** `EntityNotFoundError` is raised

### Requirement: an ambiguous company query raises AmbiguousEntityError
`resolve_vacancy` SHALL raise `AmbiguousEntityError`, carrying the
company candidates `resolve` returned, when the query matches more than
one company — the narrowing tier is never reached.

#### Scenario: two companies matching one query raise before narrowing
- **GIVEN** two companies whose display names both match a query
- **WHEN** `resolve_vacancy` is called with that query
- **THEN** `AmbiguousEntityError` is raised and its candidates name both
  companies

### Requirement: a query matching nothing raises EntityNotFoundError
`resolve_vacancy` SHALL raise `EntityNotFoundError` when the query
matches no vacancy and no company at any tier.

#### Scenario: an unmatched query raises
- **WHEN** `resolve_vacancy` is called with a string matching no vacancy
  and no company
- **THEN** `EntityNotFoundError` is raised

### Requirement: resolve_vacancy never writes and leaves resolve unchanged
`resolve_vacancy` SHALL be read-only, and `resolve`'s own behavior SHALL
be unchanged by this capability: a company-tier query passed to
`resolve` SHALL still return a `Resolution` naming that company, not a
vacancy.

#### Scenario: resolve still returns a company for a company query
- **GIVEN** a company with exactly one vacancy
- **WHEN** `resolve` is called with that company's name
- **THEN** the returned `Resolution` names the company and its
  `vacancy_id` is `None`

#### Scenario: resolving does not modify the vault
- **WHEN** `resolve_vacancy` is called with any query
- **THEN** no file in the vault is created, modified, or removed
