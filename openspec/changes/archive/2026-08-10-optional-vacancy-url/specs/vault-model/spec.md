## MODIFIED Requirements

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
