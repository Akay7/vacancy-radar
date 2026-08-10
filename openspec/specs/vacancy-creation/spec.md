# vacancy-creation Specification

## Purpose
TBD - created by openspec-sync-specs during change cli-write. Update Purpose after archive.

## Requirements

### Requirement: create_vacancy on a new company creates the company directory and _company.md
`create_vacancy` SHALL, when no company directory matching the derived
slug exists yet, create that directory and a `_company.md` for it,
alongside the new vacancy.

#### Scenario: A new company gets a directory and _company.md
- **GIVEN** a vault with no directory for the given company
- **WHEN** `create_vacancy` is called with that company's name
- **THEN** a company directory and `_company.md` are created, and the
  new vacancy is filed under it

### Requirement: create_vacancy on an existing company does not touch _company.md
`create_vacancy` SHALL, when a company directory matching the derived
slug already exists, add the new vacancy under it without modifying
that company's existing `_company.md`.

#### Scenario: Adding a second vacancy to an existing company leaves _company.md untouched
- **GIVEN** a company that already has `_company.md` and one vacancy
- **WHEN** `create_vacancy` is called again for the same company with a
  different role
- **THEN** a second vacancy directory is created and `_company.md`'s
  bytes are unchanged

### Requirement: colliding vacancy ids get distinct, suffixed ids
`create_vacancy` SHALL resolve a vacancy id collision (the same
`found_date`, company, and role slug as an existing vacancy) by minting
a distinct, suffixed id, per stage 1's `ids.new_vacancy_id`.

#### Scenario: Two same-day, same-company, unknown-role vacancies get distinct ids
- **GIVEN** a vault with one vacancy already created for a given
  company on a given date with an unknown role
- **WHEN** `create_vacancy` is called again with the same company,
  date, and unknown role
- **THEN** the two vacancies have distinct ids, and both directories
  exist afterward

### Requirement: a created vacancy is immediately retrievable
A vacancy `create_vacancy` creates SHALL be retrievable by
`list_vacancies` and by `search`, in the same process, without a
separate `reindex` call.

#### Scenario: A newly created vacancy appears in list output
- **WHEN** `create_vacancy` is called and returns successfully
- **THEN** `list_vacancies()` in the same process includes the new
  vacancy

#### Scenario: A newly created vacancy is searchable
- **WHEN** `create_vacancy` is called and returns successfully
- **THEN** a `search` call in the same process against its role or
  company text returns it as a hit

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

### Requirement: create_vacancy accepts stage_note, salary_note, recruiter, and tags as optional creation-time fields
`create_vacancy` SHALL accept four additional optional keyword
parameters — `stage_note`, `salary_note`, `recruiter` (each `str |
None`, defaulting to `None`), and `tags` (`list[str] | None`,
defaulting to `None` and treated as empty when omitted) — and forward
each to the created `Vacancy`'s corresponding field unchanged. No new
validation is added beyond what `Vacancy`'s existing field and model
validators already enforce for these fields.

#### Scenario: Provided optional fields are stored on the created vacancy
- **WHEN** `create_vacancy` is called with `stage_note`, `salary_note`,
  `recruiter`, and `tags` all provided
- **THEN** the created vacancy's frontmatter carries each value
  unchanged

#### Scenario: Omitted tags default to an empty list
- **WHEN** `create_vacancy` is called with no `tags` argument
- **THEN** the created vacancy's `tags` field is an empty list, the
  same default `Vacancy` itself uses when `tags` is unset

#### Scenario: Omitted stage_note, salary_note, and recruiter are absent
- **WHEN** `create_vacancy` is called with no `stage_note`,
  `salary_note`, or `recruiter` argument
- **THEN** the created vacancy's frontmatter carries none of those
  three fields
