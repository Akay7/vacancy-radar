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

### Requirement: Fixture generation supports a broken mode for resilience fixtures
`tests/fixtures/generate.py` SHALL support a `--broken` mode that
writes, alongside a valid vault, the malformed cases vault-reader's
resilience tests need: a `vacancy.md` with unparseable YAML, a
`vacancy.md` with an unknown status, an unreadable file, two
`vacancy.md` files sharing the same id, and a `documents/` directory
with no `vacancy.md`. Running `--broken` SHALL NOT alter the healthy
fixture tree's existing files.

#### Scenario: --broken mode adds malformed fixtures without altering the healthy tree
- **GIVEN** the fixture generator run in `--broken` mode
- **WHEN** its output is compared to the same generator run without
  `--broken`
- **THEN** every file present in the non-broken run is present,
  unchanged, in the `--broken` run
- **THEN** the `--broken` run additionally contains the malformed-YAML,
  unknown-status, unreadable-file, duplicate-id, and orphan-directory
  cases

### Requirement: The healthy fixture tree contains a vault marker
The generated vault SHALL include a `.vacancy-radar/` marker directory
at its root.

#### Scenario: the generated vault has a .vacancy-radar marker directory
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** its root directory is inspected
- **THEN** a `.vacancy-radar/` directory is present at the root

### Requirement: The healthy fixture tree includes a non-markdown document
The generated vault SHALL include at least one `takehome`-kind document
stored as a non-markdown file (not `.md`, no frontmatter), instead of
as a parsed frontmatter file.

#### Scenario: at least one takehome document is a non-markdown file
- **GIVEN** a fixture vault generated with a fixed seed
- **WHEN** the documents in it are inspected
- **THEN** at least one `documents/` directory contains a non-markdown
  file standing in for a take-home document

### Requirement: Fixture generation supports a scale override for performance tests
`generate_vault` SHALL accept optional company-count-range overrides.
When omitted, generation SHALL use the same bounds as before (so the
committed, documented-seed fixture is unaffected). When provided, they
SHALL be used to generate a larger vault (e.g. for a ~700-vacancy
performance test) without writing to the committed fixture path.

#### Scenario: a scale override produces a larger vault without touching the committed fixture
- **GIVEN** `generate_vault` called with company-count-range overrides
  sized to produce roughly 700 vacancies, targeting a temporary output
  directory
- **WHEN** generation completes
- **THEN** the temporary output directory contains roughly 700
  vacancies
- **THEN** the committed `tests/fixtures/vault/` tree is unchanged
