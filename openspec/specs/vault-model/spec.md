# vault-model Specification

## Purpose
TBD - created by archiving change vault-model. Update Purpose after archive.

## Requirements

### Requirement: Status accepts exactly the defined vocabulary
`Status` SHALL accept exactly the eight values `found`, `applied`,
`screening`, `take_home`, `interview`, `offer`, `rejected`, `ghosted`,
case-insensitively, and SHALL reject any other value with a validation
error listing the permitted values.

#### Scenario: every vocabulary value parses
- **GIVEN** each of the eight defined status strings
- **WHEN** each is parsed into `Status`
- **THEN** it parses successfully into the corresponding `Status` member

#### Scenario: unrecognized status is rejected
- **GIVEN** a status string that is not one of the eight defined values
- **WHEN** it is parsed into `Status`
- **THEN** a validation error is raised
- **THEN** the error lists the permitted status values

#### Scenario: status parsing is case-insensitive with canonical output
- **GIVEN** a status string in mixed case, e.g. `"Applied"`
- **WHEN** it is parsed into `Status`
- **THEN** it parses successfully
- **THEN** its serialized value is the canonical lowercase form,
  `"applied"`

### Requirement: Mandatory Vacancy fields are enforced
A `Vacancy` SHALL require `id`, `company`, `company_slug`, `role`,
`status`, and `found_date`. Omitting any one SHALL raise a validation
error naming the missing field. `source_url` is optional
(`str | None`, default `None`); when provided, it SHALL be rejected
unless it is an `http` or `https` URL.

#### Scenario: omitting a mandatory field is rejected
- **GIVEN** vacancy data missing one of `id`, `company`,
  `company_slug`, `role`, `status`, or `found_date`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised naming the missing field

#### Scenario: source_url must be http or https when provided
- **GIVEN** vacancy data whose `source_url` uses a scheme other than
  `http` or `https` (e.g. `ftp://example.com`)
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised

#### Scenario: source_url may be omitted
- **GIVEN** vacancy data with every mandatory field present and no
  `source_url`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** it parses successfully and its `source_url` is `None`

#### Scenario: a minimal vacancy with no optional fields parses
- **GIVEN** vacancy data with every mandatory field present and every
  optional field (`source_url`, `stage_note`, `salary_note`,
  `recruiter`, `external_id`, `tags`) absent
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** it parses successfully

### Requirement: applied_date is conditionally mandatory on status
`applied_date` SHALL be required when `status` is anything other than
`found`, and SHALL be absent or null when `status` is `found`. This
rule SHALL be enforced by a model-level validator that inspects both
fields together, not by a field-level constraint on `applied_date`
alone.

#### Scenario: non-found status without applied_date is rejected
- **GIVEN** vacancy data with `status` set to a value other than
  `found` and no `applied_date`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised explaining that `applied_date`
  is required for this status

#### Scenario: found status with applied_date present is rejected
- **GIVEN** vacancy data with `status` set to `found` and an
  `applied_date` present
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised

#### Scenario: found status with no applied_date parses
- **GIVEN** vacancy data with `status` set to `found` and no
  `applied_date`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** it parses successfully

### Requirement: Vacancy dates are coherent
`applied_date` SHALL NOT be earlier than `found_date`. `found_date`
SHALL NOT be in the future. Date fields SHALL accept both ISO date
strings and `date` objects as input.

#### Scenario: applied_date before found_date is rejected
- **GIVEN** vacancy data whose `applied_date` is earlier than its
  `found_date`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised

#### Scenario: found_date in the future is rejected
- **GIVEN** vacancy data whose `found_date` is later than today
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised

#### Scenario: applied_date equal to found_date is valid
- **GIVEN** vacancy data whose `applied_date` equals its `found_date`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** it parses successfully

#### Scenario: dates parse from strings and date objects
- **GIVEN** vacancy data whose `found_date` is given once as an ISO
  date string and once as a `date` object, with all else equal
- **WHEN** a `Vacancy` is constructed from each form
- **THEN** both parse successfully to the same `date` value

### Requirement: Role is non-empty, with a designated placeholder
`role` SHALL reject empty or whitespace-only values. The literal value
`"unknown"` (case-insensitively, ignoring surrounding whitespace) SHALL
be accepted and SHALL mark `role_is_placeholder` as `True`; every other
non-empty value SHALL leave `role_is_placeholder` `False`.

#### Scenario: empty or whitespace-only role is rejected
- **GIVEN** vacancy data whose `role` is empty or consists only of
  whitespace
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** a validation error is raised

#### Scenario: role "unknown" parses successfully
- **GIVEN** vacancy data whose `role` is `"unknown"`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** it parses successfully

#### Scenario: role_is_placeholder is True for unknown in any case or spacing
- **GIVEN** vacancy data whose `role` is `"unknown"`, `"Unknown"`, or
  `" UNKNOWN "`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** `role_is_placeholder` is `True`

#### Scenario: role_is_placeholder is False for other values
- **GIVEN** vacancy data whose `role` is a non-empty value other than a
  case/whitespace variant of `"unknown"`, e.g. `"developer"`
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** `role_is_placeholder` is `False`

### Requirement: stage_note is preserved verbatim
`stage_note`, when present, SHALL round-trip exactly as given, including
embedded newlines, emoji, and mixed Cyrillic/Latin text.

#### Scenario: stage_note preserves exact text
- **GIVEN** vacancy data whose `stage_note` contains newlines, emoji,
  and mixed Cyrillic/Latin text
- **WHEN** a `Vacancy` is constructed from that data and its
  `stage_note` is read back
- **THEN** the value read back is identical, character for character,
  to the original text

### Requirement: company and company_slug are both preserved independently
`company` SHALL preserve the original, possibly non-ascii, display
name. `company_slug` SHALL be a separate ascii field. Both SHALL
round-trip intact together.

#### Scenario: non-ascii company round-trips with its ascii slug
- **GIVEN** vacancy data with `company` set to the placeholder
  `"Незабудка Банк"` and `company_slug` set to a corresponding ascii
  slug
- **WHEN** a `Vacancy` is constructed from that data
- **THEN** `company` reads back as `"Незабудка Банк"` unchanged
- **THEN** `company_slug` reads back as the ascii slug, unchanged

### Requirement: Vacancies sort by applied_date, falling back to found_date
Vacancies SHALL sort in descending order by `applied_date`, using
`found_date` in its place for vacancies with status `found` (which have
no `applied_date`). The sort SHALL be stable for ties.

#### Scenario: vacancies sort by applied_date descending
- **GIVEN** a list of vacancies with distinct `applied_date` values
- **WHEN** the list is sorted using the vault-model ordering
- **THEN** vacancies appear in descending order of `applied_date`

#### Scenario: found vacancies sort by found_date in applied_date's place
- **GIVEN** a list including vacancies with status `found` (no
  `applied_date`) interleaved with vacancies that have `applied_date`
- **WHEN** the list is sorted using the vault-model ordering
- **THEN** each `found` vacancy is ordered as if its `found_date` were
  its sort key

#### Scenario: ties are broken stably
- **GIVEN** two vacancies with the same effective sort date, in a
  known relative input order
- **WHEN** the list is sorted using the vault-model ordering
- **THEN** their relative order in the output matches their relative
  order in the input
</content>
