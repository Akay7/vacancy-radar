# vacancy-editing Specification

## Purpose
Defines `core.edit_vacancy` — the single validated, atomic write that
corrects a vacancy's stored frontmatter fields. Covers which ten fields are
editable (and why `id`, `status`, `company`, and `company_slug` are not),
how a field is set versus cleared, whole-model validation before any write,
no-op semantics, preservation of every untouched line, and the eager index
refresh. Field names passed as strings by the CLI and MCP surfaces are
validated here too, not in those surfaces.

## Requirements

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

### Requirement: an omitted field is left alone and a field given as None is cleared
`edit_vacancy` SHALL default every field parameter to a module-level
`UNSET` sentinel. A parameter left at `UNSET` SHALL leave that field's
stored value untouched. A nullable field passed explicitly as `None`
SHALL be removed from the vacancy's frontmatter.

#### Scenario: omitted fields are untouched
- **GIVEN** a vacancy with a `recruiter`, a `salary_note`, and a
  `source_url`
- **WHEN** `edit_vacancy` is called with only `source_url` given
- **THEN** `recruiter` and `salary_note` are unchanged and `source_url`
  carries the new value

#### Scenario: an explicit None clears a nullable field
- **GIVEN** a vacancy with a non-empty `recruiter`
- **WHEN** `edit_vacancy` is called with `recruiter=None`
- **THEN** `recruiter` is absent from the vacancy's frontmatter
  afterward

#### Scenario: UNSET is distinguishable from None
- **WHEN** `edit_vacancy` is called with no field arguments at all, and
  again with `recruiter=None`
- **THEN** the first call clears nothing and the second clears
  `recruiter`

### Requirement: multiple fields are set in one atomic write
`edit_vacancy` SHALL apply every given field in a single write of
`vacancy.md`. When validation rejects the merged result, no field
SHALL be written — the file's bytes SHALL be unchanged.

#### Scenario: several fields change in one call
- **WHEN** `edit_vacancy` is called with `source_url`, `recruiter`, and
  `tags` all given
- **THEN** all three carry their new values afterward, and the file was
  written once

#### Scenario: a rejected multi-field edit writes nothing
- **GIVEN** a vacancy.md read into text before the call
- **WHEN** `edit_vacancy` is called with one valid field value and one
  that makes the merged vacancy invalid
- **THEN** a typed error is raised and the file's bytes are identical
  to before the call, including the valid field's old value

### Requirement: the merged vacancy is validated before writing
`edit_vacancy` SHALL construct a `Vacancy` from the merged frontmatter
before writing, and SHALL raise `InvalidVacancyDataError` wrapping the
underlying validation error when that construction fails. This applies
to cross-field rules, including rules about fields the caller did not
give.

#### Scenario: an invalid source_url scheme is rejected
- **WHEN** `edit_vacancy` is called with a `source_url` whose scheme is
  neither `http` nor `https`
- **THEN** `InvalidVacancyDataError` is raised and the vacancy is
  unchanged

#### Scenario: an empty role is rejected
- **WHEN** `edit_vacancy` is called with a `role` that is empty or
  whitespace-only
- **THEN** `InvalidVacancyDataError` is raised and the vacancy is
  unchanged

#### Scenario: clearing applied_date on a non-found vacancy is rejected
- **GIVEN** a vacancy whose status is `applied`
- **WHEN** `edit_vacancy` is called with `applied_date=None`
- **THEN** `InvalidVacancyDataError` is raised, its message names
  `applied_date`, and the vacancy is unchanged

#### Scenario: a found_date later than the stored applied_date is rejected
- **GIVEN** a vacancy with both a `found_date` and a later
  `applied_date`
- **WHEN** `edit_vacancy` is called with a `found_date` later than that
  stored `applied_date`
- **THEN** `InvalidVacancyDataError` is raised and the vacancy is
  unchanged

#### Scenario: a future found_date is rejected
- **WHEN** `edit_vacancy` is called with a `found_date` later than
  today
- **THEN** `InvalidVacancyDataError` is raised and the vacancy is
  unchanged

### Requirement: edit_vacancy returns an EditResult naming what changed
`edit_vacancy` SHALL return an `EditResult` carrying the vacancy id, a
`changed` flag, and the set of field names whose stored values actually
changed, each with its old and new value.

#### Scenario: the result names only the fields that actually changed
- **GIVEN** a vacancy whose `recruiter` is already `"Anna K."`
- **WHEN** `edit_vacancy` is called with that same `recruiter` and a
  new `source_url`
- **THEN** the returned `EditResult` reports `changed` true and names
  `source_url` only

### Requirement: a no-op edit writes nothing and does not reindex
`edit_vacancy` SHALL treat a call with no field arguments, or one in
which every given value already equals the vacancy's stored value, as a
no-op: it SHALL return an `EditResult` with `changed` false and no
changed fields, SHALL NOT write `vacancy.md`, and SHALL NOT trigger a
reindex. Equality SHALL be compared on parsed `Vacancy` values, not raw
YAML text, so an empty `tags` list and an absent `tags` field compare
equal.

#### Scenario: an edit with no fields given changes nothing
- **GIVEN** a vacancy.md read into text before the call
- **WHEN** `edit_vacancy` is called with no field arguments
- **THEN** the returned result reports `changed` false and the file's
  bytes are unchanged

#### Scenario: re-applying the same values is a no-op
- **WHEN** `edit_vacancy` is called twice with identical field values
- **THEN** the second call reports `changed` false and the file's bytes
  are identical to those after the first call

#### Scenario: an empty tags list equals an absent tags field
- **GIVEN** a vacancy with no `tags` in its frontmatter
- **WHEN** `edit_vacancy` is called with `tags=[]`
- **THEN** the result reports `changed` false and the file is unchanged

### Requirement: an unknown vacancy raises without writing
`edit_vacancy` SHALL raise `EntityNotFoundError` when its
`vacancy_id` names no vacancy in the vault, before performing any
write.

#### Scenario: editing an unknown vacancy raises
- **WHEN** `edit_vacancy` is called with an id present in no vacancy
- **THEN** `EntityNotFoundError` is raised and no file in the vault is
  modified

### Requirement: edit_vacancy preserves every untouched line of vacancy.md
`edit_vacancy` SHALL change only the frontmatter keys corresponding to
fields whose values changed, plus the appended edit-history entries.
Every other line — other frontmatter keys, their comments and quoting
style, and all other body content — SHALL be byte-identical before and
after the call.

#### Scenario: a round trip differs only in the edited keys and the history block
- **GIVEN** a vacancy.md with a hand-written body and comments in its
  frontmatter, read into text before the call
- **WHEN** `edit_vacancy` changes one field and the file is read again
- **THEN** the only differing lines are that field's frontmatter key
  and the appended edit-history entry

#### Scenario: the role H1 in the body is not rewritten
- **GIVEN** a vacancy whose body begins with a `# <role>` heading
- **WHEN** `edit_vacancy` changes `role`
- **THEN** the `# <role>` heading line is unchanged

### Requirement: edit_vacancy does not change the vacancy's id, directory, or status
`edit_vacancy` SHALL leave the vacancy's `id`, its directory location,
its `company`/`company_slug`, and its `status` untouched, including
when `found_date` or `role` — which contributed to the id when it was
minted — are edited.

#### Scenario: editing found_date leaves the id and directory alone
- **GIVEN** a vacancy whose id encodes its original `found_date`
- **WHEN** `edit_vacancy` changes `found_date`
- **THEN** the vacancy's `id`, its directory path, and its `vacancy.md`
  path are all unchanged, and it is still retrievable by its original
  id

#### Scenario: status is unchanged by any edit
- **GIVEN** a vacancy at status `screening`
- **WHEN** `edit_vacancy` changes any editable field
- **THEN** the vacancy's `status` afterward is still `screening`

### Requirement: an applied edit is reflected in the index without a separate reindex
`edit_vacancy` SHALL refresh the index before returning, so an edited
value is visible to `list_vacancies`, `get_vacancy`, and `search` in
the same process without a separate `reindex` call.

#### Scenario: an edited role is searchable immediately
- **WHEN** `edit_vacancy` changes a vacancy's `role` from `unknown` to
  a real title
- **THEN** a `search` call in the same process against the new title
  returns that vacancy as a hit

#### Scenario: an edited field is visible to get_vacancy immediately
- **WHEN** `edit_vacancy` changes a vacancy's `source_url`
- **THEN** `get_vacancy` in the same process reports the new
  `source_url`

### Requirement: field names passed as strings are validated with typed errors
The core module SHALL expose the editable field set, plus typed errors
for callers that name fields as strings rather than as keyword
arguments (the CLI and MCP surfaces): `UneditableFieldError` for a
name that is not an editable field, `NotNullableFieldError` for a
request to clear `role`, `found_date`, or `tags`, and
`ConflictingEditError` for a field both given a value and named for
clearing.

#### Scenario: clearing an uneditable field name raises
- **WHEN** a caller requests that `status` or an unknown field name be
  cleared
- **THEN** `UneditableFieldError` is raised, naming the field and
  listing the editable fields, and nothing is written

#### Scenario: clearing a non-nullable field raises
- **WHEN** a caller requests that `role`, `found_date`, or `tags` be
  cleared
- **THEN** `NotNullableFieldError` is raised naming that field, and
  nothing is written

#### Scenario: setting and clearing the same field raises
- **WHEN** a caller both gives a value for `recruiter` and names
  `recruiter` for clearing
- **THEN** `ConflictingEditError` is raised naming that field, and
  nothing is written
