## MODIFIED Requirements

### Requirement: the four write tools carry readOnlyHint false and destructiveHint false
Every write tool SHALL declare `annotations.readOnlyHint = false` and
`annotations.destructiveHint = false` — `append_note`, `set_status`,
`edit_vacancy`, `add_document`, and `create_vacancy`.

#### Scenario: every write tool's annotations report readOnlyHint false and destructiveHint false
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of the write tools' `annotations.readOnlyHint` is
  `false` and `annotations.destructiveHint` is `false`

### Requirement: no exposed write tool can delete or overwrite vault content
No tool this change exposes SHALL delete a vault file, and none SHALL
overwrite an existing document or note file. The in-place `vacancy.md`
frontmatter updates performed by `set_status` and `edit_vacancy` are
the sole exceptions, and each SHALL preserve the file's body content
outside the fields it changes and the history entry it appends.

#### Scenario: add_document never overwrites an existing document
- **GIVEN** a vacancy with an existing document at the path
  `add_document` would derive for a given `date`/`kind`/`title`
- **WHEN** the `add_document` tool is called with those same
  `date`/`kind`/`title`
- **THEN** the existing document's content is unchanged and the tool
  either files a collision-suffixed new document or reports the dedupe
  outcome, per `core.add_document`'s own behavior — no existing file's
  bytes are altered

#### Scenario: no delete-capable tool is exposed
- **WHEN** the server's `tools/list` response is fetched
- **THEN** no listed tool accepts an argument or performs an operation
  that removes a file from the vault

#### Scenario: edit_vacancy touches no file but the target vacancy.md
- **GIVEN** a vacancy with documents filed under it
- **WHEN** the `edit_vacancy` tool applies a change
- **THEN** only that vacancy's `vacancy.md` is modified, and every
  document file's bytes are unchanged

## ADDED Requirements

### Requirement: the edit_vacancy tool delegates to exactly one core.py function
The `edit_vacancy` tool SHALL, with `core.py` mocked, call
`core.edit_vacancy` exactly once and return that call's result
unmodified apart from serialization. It SHALL contain no field
validation, no history formatting, and no other business rule of its
own.

#### Scenario: edit_vacancy tool delegates to core.edit_vacancy
- **GIVEN** `core.edit_vacancy` is mocked to return a fixed
  `EditResult`
- **WHEN** the `edit_vacancy` tool is called with `vacancy_id="v-1"`
  and `source_url="https://acme.example/2"`
- **THEN** `core.edit_vacancy` is called exactly once with those
  arguments and the tool result matches the mocked `EditResult`,
  serialized, unmodified

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
  `tags`, `found_date`, `applied_date`, and `clear`, and `vacancy_id`
  is its only required property

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

### Requirement: an edit_vacancy tool call that core.py rejects returns a typed error result
The `edit_vacancy` tool SHALL, when `core.edit_vacancy` raises any
typed error — invalid vacancy data, an unknown vacancy, an uneditable
or non-nullable field name, or a conflicting set-and-clear — produce a
tool result reporting that error rather than raising an unhandled
exception out of the handler, and no vault file SHALL be modified.

#### Scenario: an invalid source_url returns a typed error result
- **GIVEN** a real vault (no mocking of `core.edit_vacancy`)
- **WHEN** the `edit_vacancy` tool is called with a `source_url` whose
  scheme is neither `http` nor `https`
- **THEN** the tool call returns without raising, the result reports an
  error naming `InvalidVacancyDataError`, and the vacancy is unchanged

#### Scenario: clearing an uneditable field returns a typed error result
- **GIVEN** a real vault
- **WHEN** the `edit_vacancy` tool is called with `clear=["status"]`
- **THEN** the tool call returns without raising, the result reports an
  error naming `UneditableFieldError`, and the vacancy is unchanged

#### Scenario: an unknown vacancy returns a typed error result
- **WHEN** the `edit_vacancy` tool is called with a `vacancy_id` no
  vacancy carries
- **THEN** the tool call returns without raising and the result reports
  an error naming `EntityNotFoundError`

### Requirement: an edited value is visible to the read tools without a separate reindex
A vacancy edited through the `edit_vacancy` tool SHALL be reported with
its new values by `get_vacancy` and `list_vacancies`, and matched by
`search` against newly-set text, in the same server process without any
reindex call.

#### Scenario: an edited role is returned by get_vacancy immediately
- **WHEN** the `edit_vacancy` tool changes a vacancy's `role` and the
  `get_vacancy` tool is then called for that vacancy
- **THEN** the returned detail reports the new role
