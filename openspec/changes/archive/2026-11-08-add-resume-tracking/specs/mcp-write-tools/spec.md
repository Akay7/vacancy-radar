## MODIFIED Requirements

### Requirement: write tool argument names match core.py parameter names
Every argument a write tool's schema declares SHALL share its name
with the `core.py` parameter it is passed as.

#### Scenario: add_document tool argument names match core.add_document's signature
- **WHEN** the `add_document` tool's schema is inspected
- **THEN** its parameter names are exactly
  `{vacancy_id, kind, content, title, date, external_id}`, matching
  `core.add_document`'s own positional/keyword parameter names exactly

#### Scenario: set_status tool argument names match core.set_status's signature
- **WHEN** the `set_status` tool's schema is inspected
- **THEN** its parameter names are a subset of
  `{vacancy_id, new_status, note, applied_date, resume, force}`,
  matching `core.set_status`'s own parameter names exactly

#### Scenario: create_vacancy tool argument names match core.create_vacancy's signature
- **WHEN** the `create_vacancy` tool's schema is inspected
- **THEN** its parameter names are exactly
  `{company, role, source_url, found_date, status, applied_date,
  stage_note, salary_note, recruiter, tags, resume}`, matching
  `core.create_vacancy`'s own parameter names exactly

### Requirement: the edit_vacancy tool exposes one optional parameter per editable field, plus clear
The `edit_vacancy` tool's schema SHALL declare `vacancy_id` as its only
required parameter, one optional parameter per editable field named
exactly as `core.edit_vacancy`'s own parameter, and an optional
`clear` array of field names. It SHALL declare no parameter for `id`,
`status`, `company`, or `company_slug`.

#### Scenario: the schema declares every editable field and nothing more
- **WHEN** the `edit_vacancy` tool's schema is inspected
- **THEN** its properties are exactly `vacancy_id`, `source_url`,
  `role`, `stage_note`, `salary_note`, `recruiter`, `external_id`,
  `tags`, `found_date`, `applied_date`, `resume`, and `clear`, and
  `vacancy_id` is its only required property

#### Scenario: omitted field parameters leave those fields untouched
- **GIVEN** a real vault with a vacancy carrying a `recruiter`
- **WHEN** the `edit_vacancy` tool is called with only `vacancy_id` and
  `source_url`
- **THEN** the vacancy's `recruiter` is unchanged and its `source_url`
  carries the new value

#### Scenario: clear removes the named nullable fields
- **GIVEN** a real vault with a vacancy carrying a `recruiter`
- **WHEN** the `edit_vacancy` tool is called with
  `clear=["recruiter"]`
- **THEN** `recruiter` is absent from that vacancy's frontmatter
  afterward

#### Scenario: clear removes a resume
- **GIVEN** a real vault with a vacancy carrying a `resume`
- **WHEN** the `edit_vacancy` tool is called with `clear=["resume"]`
- **THEN** `resume` is absent from that vacancy's frontmatter
  afterward
