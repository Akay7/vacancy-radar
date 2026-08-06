## ADDED Requirements

### Requirement: get_company returns every vacancy for that company across time
`get_company(name)` SHALL resolve `name` and return every vacancy
belonging to that company, spanning the vault's oldest and newest
records — not just recent ones.

#### Scenario: A company with several vacancies returns all of them, oldest and newest
- **WHEN** `get_company` is called for a company with vacancies
  spanning a wide date range
- **THEN** the returned `CompanyDossier` includes both the oldest and
  the newest vacancy for that company

### Requirement: recruiters and domains come from _company.md
`get_company(name)` SHALL populate `recruiters` and `domains` from the
company's `_company.md` frontmatter, when present.

#### Scenario: Recruiters and domains come from _company.md
- **WHEN** `get_company` is called for a company whose `_company.md`
  lists recruiters and domains
- **THEN** the returned `CompanyDossier`'s `recruiters` and `domains`
  match `_company.md`'s values

### Requirement: a company with no _company.md still returns its vacancies, with a warning
`get_company(name)` SHALL succeed for a company with no `_company.md`,
returning its vacancies with empty `recruiters`/`domains`/`notes` and
a warning noting the missing file — never raising.

#### Scenario: A company with no _company.md still returns its vacancies, with a warning
- **WHEN** `get_company` is called for a company directory with
  vacancies but no `_company.md`
- **THEN** the returned `CompanyDossier` includes those vacancies and
  a warning naming the missing `_company.md`, and no exception is
  raised

### Requirement: dossier output is bounded to paths and counts, never document bodies
`get_company`'s per-vacancy document information SHALL be limited to
counts and paths — never document text — regardless of how many
vacancies or documents the company has.

#### Scenario: Output is bounded: document counts and paths, never bodies
- **WHEN** `get_company` is called for a company with four vacancies,
  each with several documents
- **THEN** the returned `CompanyDossier` reports each vacancy's
  document count, and no document body appears anywhere in the result
