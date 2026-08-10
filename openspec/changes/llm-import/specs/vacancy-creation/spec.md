## ADDED Requirements

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
