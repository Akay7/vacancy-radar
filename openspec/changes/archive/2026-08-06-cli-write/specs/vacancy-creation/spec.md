## ADDED Requirements

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
