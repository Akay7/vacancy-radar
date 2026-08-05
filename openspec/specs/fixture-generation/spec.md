# fixture-generation Specification

## Purpose
TBD - created by archiving change vault-model. Update Purpose after archive.

## Requirements

### Requirement: Fixture generation is seeded and deterministic
`tests/fixtures/generate.py` SHALL produce byte-identical output trees
when run twice with the same seed.

#### Scenario: same seed produces identical output
- **GIVEN** a fixed seed
- **WHEN** the fixture generator is run twice with that seed, into two
  separate output locations
- **THEN** the two resulting file trees are byte-identical, file for
  file

### Requirement: Generated fixtures cover every Status value
The generated fixture vault SHALL include at least one vacancy for
every `Status` value.

#### Scenario: every status appears at least once
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** the vacancies in it are inspected
- **THEN** every `Status` value appears on at least one vacancy

### Requirement: Generated fixtures include repeat applications across years
The generated fixture vault SHALL include at least two companies with
vacancies found in different calendar years.

#### Scenario: at least two companies have vacancies spanning years
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** the vacancies in it are grouped by company
- **THEN** at least two companies each have at least two vacancies
  whose `found_date` values fall in different calendar years

### Requirement: Generated fixtures include unknown-role vacancies
The generated fixture vault SHALL include at least three vacancies with
`role` set to `UNKNOWN_ROLE` and `tags` including `needs_review`.

#### Scenario: at least three vacancies are unknown-role and flagged
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** the vacancies in it are inspected
- **THEN** at least three vacancies have `role_is_placeholder` `True`
- **THEN** each of those vacancies has `needs_review` in its `tags`

### Requirement: Generated fixtures include non-ascii company names and no real entities
The generated fixture vault SHALL include at least one non-ascii
company name, and SHALL NOT contain any real company, person, or
address.

#### Scenario: at least one company name is non-ascii
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** the companies in it are inspected
- **THEN** at least one company's `name` contains non-ascii characters

#### Scenario: generated content is synthetic
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** its companies, recruiters, and generated email bodies are
  inspected
- **THEN** none of them matches a real company, person, or address —
  all content is drawn from the generator's synthetic data
</content>
