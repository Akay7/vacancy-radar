## RENAMED Requirements

- FROM: `### Requirement: edit_vacancy edits exactly nine named fields`
- TO: `### Requirement: edit_vacancy edits exactly ten named fields`

## MODIFIED Requirements

### Requirement: edit_vacancy edits exactly ten named fields
`core.edit_vacancy` SHALL accept, as keyword parameters, exactly these
editable fields: `source_url`, `role`, `stage_note`, `salary_note`,
`recruiter`, `external_id`, `tags`, `found_date`, `applied_date`, and
`resume`. It SHALL NOT accept `id`, `status`, `company`, or
`company_slug` as parameters — the signature itself is what makes
those uneditable, with no runtime allow-list. `resume` SHALL be
clearable like the other nullable fields.

#### Scenario: each editable field can be set through the function
- **GIVEN** an existing vacancy
- **WHEN** `edit_vacancy` is called once per editable field, each time
  with a new valid value for that field
- **THEN** each call succeeds and the vacancy's frontmatter carries the
  new value for that field

#### Scenario: an uneditable field is not a parameter
- **WHEN** `edit_vacancy` is called with `status=`, `company=`,
  `company_slug=`, or `id=`
- **THEN** the call raises `TypeError` and nothing in the vault is
  modified

#### Scenario: resume can be set and then cleared
- **GIVEN** a vacancy with no `resume`
- **WHEN** `edit_vacancy` is called with `resume="backend-v2"`, then
  with `resume=None`
- **THEN** the vacancy's frontmatter carries `resume: backend-v2` after
  the first call and no `resume` key after the second, and each call
  appended an `## Edit History` entry
