## ADDED Requirements

### Requirement: find_existing's source_url parameter is optional
`find_existing` SHALL accept `source_url` as optional (`str | None`,
defaulting to `None`). When omitted, matching SHALL be limited to the
company tier — the caller may have no `source_url` to check against
at all (e.g. a recruiter sent only a PDF, no posting link).

#### Scenario: find_existing with no source_url still matches by company
- **GIVEN** a vault company with vacancies
- **WHEN** `find_existing` is called with that company's name and no
  `source_url` argument
- **THEN** the returned list contains that company's vacancies

### Requirement: find_existing never matches two vacancies solely because both lack a source_url
`find_existing`'s `source_url` tier SHALL only ever contribute a match
when the given `source_url` is not `None` and equals a vacancy's own
non-`None` `source_url` exactly. Two vacancies that both have no
`source_url` SHALL NOT be treated as matching each other on that
basis.

#### Scenario: A URL-less vacancy under a different company is not returned as a false match
- **GIVEN** two vacancies under different companies, neither with a
  `source_url`
- **WHEN** `find_existing` is called with the first vacancy's company
  and no `source_url` argument
- **THEN** the returned list does not include the second vacancy

#### Scenario: Omitting source_url never matches via the source_url tier
- **GIVEN** a vault with several vacancies that have no `source_url`
- **WHEN** `find_existing` is called with a company that resolves to
  none of them and no `source_url` argument
- **THEN** the returned list is empty, even though other vacancies in
  the vault also have no `source_url`
