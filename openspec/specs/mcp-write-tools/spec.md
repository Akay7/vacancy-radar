# mcp-write-tools

## Purpose
Defines the MCP server's four write tools — `append_note`, `set_status`,
`add_document`, `create_vacancy` — each a thin delegation to a single
`core.py` call, with schemas mirroring `core.py`'s own parameter names and
`models.py`-derived enums, and with safety guarantees: no delete, no
overwrite (beyond `set_status`'s in-place frontmatter update), and no
caller-supplied filesystem path.

## Requirements

### Requirement: each write tool delegates to exactly one core.py function
`append_note`, `set_status`, `add_document`, and `create_vacancy` SHALL
each, with `core.py` mocked, call exactly one `core.py` function and
return that call's result unmodified apart from serialization and, for
`create_vacancy`, the id derived from the returned path's parent
directory name (design.md decision 7). Neither the tool module nor any
tool handler SHALL contain filtering, sorting, path manipulation, or
other business rules of its own.

#### Scenario: append_note tool delegates to core.append_note
- **GIVEN** `core.append_note` is mocked to return a fixed `Path`
- **WHEN** the `append_note` tool is called with `vacancy_id="v-1"`,
  `text="called back"`
- **THEN** `core.append_note` is called exactly once with
  `vacancy_id="v-1"`, `text="called back"` and the tool result reports
  the mocked path, unmodified

#### Scenario: set_status tool delegates to core.set_status
- **GIVEN** `core.set_status` is mocked to return a fixed `StatusChange`
- **WHEN** the `set_status` tool is called with `vacancy_id="v-1"`,
  `new_status="screening"`
- **THEN** `core.set_status` is called exactly once with
  `vacancy_id="v-1"`, `new_status="screening"` and the tool result
  matches the mocked `StatusChange`, serialized, unmodified

#### Scenario: add_document tool delegates to core.add_document
- **GIVEN** `core.add_document` is mocked to return a fixed `Path`
- **WHEN** the `add_document` tool is called with `vacancy_id="v-1"`,
  `kind="email"`, `content="..."`, `title="Follow up"`,
  `date="2026-08-06"`
- **THEN** `core.add_document` is called exactly once with those
  arguments and the tool result reports the mocked path, unmodified

#### Scenario: create_vacancy tool delegates to core.create_vacancy
- **GIVEN** `core.create_vacancy` is mocked to return a fixed `Path`
  whose parent directory is named `"2026-08-10-acme-corp-backend"`
- **WHEN** the `create_vacancy` tool is called with `company="Acme
  Corp"`, `role="Backend Engineer"`, `source_url="https://acme.example/
  1"`, `found_date="2026-08-10"`, `status="found"`
- **THEN** `core.create_vacancy` is called exactly once with those
  arguments and the tool result reports the mocked path and the id
  `"2026-08-10-acme-corp-backend"`, computed only from the mocked
  path's own structure

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

### Requirement: every write tool exposes a valid JSON schema
Each of the four write tools SHALL declare an `inputSchema` that is
valid JSON Schema, listed in the server's `tools/list` response.

#### Scenario: every write tool's schema validates as JSON Schema
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of `append_note`, `set_status`, `add_document`,
  `create_vacancy` is present, and each one's `inputSchema` validates
  successfully against the JSON Schema meta-schema

### Requirement: enum-typed write tool parameters enumerate permitted values from models.py
An enum-typed write tool parameter SHALL declare its permitted values
from `models.py`: `set_status`'s `new_status` from `Status`,
`add_document`'s `kind` from `DocumentKind`, `create_vacancy`'s
`status` from `Status` — never a literal list written into the server
module.

#### Scenario: add_document tool's kind enum matches DocumentKind's members
- **WHEN** the `add_document` tool's schema is inspected
- **THEN** its `kind` parameter's `enum` values equal
  `[k.value for k in DocumentKind]` exactly

#### Scenario: set_status tool's new_status enum matches Status's members
- **WHEN** the `set_status` tool's schema is inspected
- **THEN** its `new_status` parameter's `enum` values equal
  `[s.value for s in Status]` exactly

#### Scenario: create_vacancy tool's status enum matches Status's members
- **WHEN** the `create_vacancy` tool's schema is inspected
- **THEN** its `status` parameter's `enum` values equal
  `[s.value for s in Status]` exactly

### Requirement: optional write tool parameters are genuinely optional
A write tool parameter SHALL stay optional in the tool's schema
whenever it is optional in `core.py`'s own signature, and omitting it
SHALL produce the same `core.py` call as passing `core.py`'s own
default for that parameter.

#### Scenario: omitting append_note's date matches core's own default
- **GIVEN** `core.append_note` is mocked
- **WHEN** the `append_note` tool is called with no `date` argument
- **THEN** `core.append_note` is called with `date=None`, letting
  `core.append_note` resolve today's local date itself, exactly as an
  unset `date` already behaves when calling `core.append_note` directly

#### Scenario: omitting add_document's external_id matches core's own default
- **GIVEN** `core.add_document` is mocked
- **WHEN** the `add_document` tool is called with no `external_id`
  argument
- **THEN** `core.add_document` is called with `external_id=None`

#### Scenario: omitting create_vacancy's optional fields matches core's own defaults
- **GIVEN** `core.create_vacancy` is mocked
- **WHEN** the `create_vacancy` tool is called with no `source_url`,
  `applied_date`, `stage_note`, `salary_note`, `recruiter`, or `tags`
  argument
- **THEN** `core.create_vacancy` is called with `source_url=None`,
  `applied_date=None`, `stage_note=None`, `salary_note=None`,
  `recruiter=None`, `tags=None` — exactly what each parameter already
  defaults to when calling `core.create_vacancy` directly

### Requirement: an out-of-range write tool argument returns a typed error, not a raised exception
A write tool call SHALL, when an argument is outside its declared enum
or `core.py` rejects it for another typed reason (an invalid
transition, a nonexistent vacancy, invalid vacancy data), produce a
tool result reporting the typed error rather than raising an unhandled
exception out of the tool handler.

#### Scenario: set_status with an unreachable transition returns a typed error result
- **GIVEN** `core.set_status` is mocked to raise
  `core.InvalidStatusTransitionError`
- **WHEN** the `set_status` tool is called with a backward transition
  and no `force` argument
- **THEN** the tool call returns without raising, and the tool result
  reports an error naming `InvalidStatusTransitionError`

#### Scenario: create_vacancy with a non-found status and no applied_date returns a typed error naming the rule
- **GIVEN** a real vault (no mocking of `core.create_vacancy`)
- **WHEN** the `create_vacancy` tool is called with `status="applied"`
  and no `applied_date`
- **THEN** the tool call returns without raising, the tool result
  reports an error naming `InvalidVacancyDataError` whose message
  states that `applied_date` is required for that status, and no
  company directory or vacancy file is created

#### Scenario: create_vacancy with applied_date earlier than found_date returns a typed error
- **GIVEN** a real vault (no mocking of `core.create_vacancy`)
- **WHEN** the `create_vacancy` tool is called with `applied_date`
  earlier than `found_date`
- **THEN** the tool call returns without raising, the tool result
  reports an error naming `InvalidVacancyDataError`, and no company
  directory or vacancy file is created

### Requirement: the four write tools carry readOnlyHint false and destructiveHint false
Every write tool SHALL declare `annotations.readOnlyHint = false` and
`annotations.destructiveHint = false` — `append_note`, `set_status`,
`edit_vacancy`, `add_document`, and `create_vacancy`.

#### Scenario: every write tool's annotations report readOnlyHint false and destructiveHint false
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of the write tools' `annotations.readOnlyHint` is
  `false` and `annotations.destructiveHint` is `false`

### Requirement: add_document derives its filename from date and title, never from a caller-supplied path
`add_document`'s tool SHALL expose no path-shaped argument; the filed
document's location SHALL be derived by `core.add_document` from
`date`, `kind`, and `title`, and the resulting path SHALL always be
inside the target vacancy's own `documents/` directory, even when
`title` contains path separators or `..` segments.

#### Scenario: a title containing separators produces a path inside the target directory
- **GIVEN** a vacancy with an existing `documents/` directory
- **WHEN** the `add_document` tool is called with
  `title="../../etc/passwd"` and otherwise valid arguments
- **THEN** the created document's path is inside that vacancy's
  `documents/` directory, and no file is created anywhere outside it

#### Scenario: add_document's schema declares no path argument
- **WHEN** the `add_document` tool's schema is inspected
- **THEN** it declares no argument accepting a filesystem path for
  writing

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

### Requirement: create_vacancy tool creates a new company's directory and _company.md
The `create_vacancy` tool SHALL, for a company with no existing
directory, create that directory and a `_company.md` for it alongside
the new vacancy — the same behavior `core.create_vacancy` already
guarantees, exercised end to end through the tool.

#### Scenario: A new company gets a directory through the tool
- **GIVEN** a vault with no directory for a given company
- **WHEN** the `create_vacancy` tool is called with that company's name
  and otherwise valid arguments
- **THEN** a company directory and `_company.md` are created, and the
  new vacancy is filed under it

### Requirement: create_vacancy tool adds to an existing company without touching _company.md
The `create_vacancy` tool SHALL, for a company that already has a
directory, add the new vacancy under it without modifying that
company's existing `_company.md`.

#### Scenario: A second vacancy through the tool leaves _company.md untouched
- **GIVEN** a company that already has `_company.md` and one vacancy
- **WHEN** the `create_vacancy` tool is called again for the same
  company with a different role
- **THEN** a second vacancy directory is created and `_company.md`'s
  bytes are unchanged

### Requirement: a vacancy created through the create_vacancy tool is immediately listed and searchable
A vacancy created by the `create_vacancy` tool SHALL appear in the
`list_vacancies` tool's output and be findable via the `search` tool,
in the same process, without a separate `reindex` call.

#### Scenario: A newly created vacancy appears in the list_vacancies tool's output
- **WHEN** the `create_vacancy` tool is called and returns successfully
- **THEN** the `list_vacancies` tool, called in the same process,
  includes the new vacancy

#### Scenario: A newly created vacancy is found by the search tool
- **WHEN** the `create_vacancy` tool is called and returns successfully
- **THEN** the `search` tool, called in the same process against its
  role or company text, returns it as a hit

### Requirement: create_vacancy tool mints distinct ids for a same-day, same-company, unknown-role collision
The `create_vacancy` tool SHALL produce two vacancies with distinct
ids when called twice for the same company, the same `found_date`,
and no distinguishing role.

#### Scenario: Two same-day, same-company, unknown-role vacancies get distinct ids through the tool
- **GIVEN** a vault with one vacancy already created through the tool
  for a given company, date, and unknown role
- **WHEN** the `create_vacancy` tool is called again with the same
  company, date, and unknown role
- **THEN** the two tool calls report distinct ids, and both vacancy
  directories exist afterward

### Requirement: create_vacancy's tool description states the import conventions a caller must apply itself
The `create_vacancy` tool's description SHALL state, in terms a
calling model can act on without consulting other documentation: that
`role` should be `"unknown"` when no title is available and such
vacancies should be tagged `needs_review`; that `found_date` may be
synthesized from `applied_date` when the source has no found date, and
such records should be tagged `migrated`; that `source_url` may be
omitted when the source has no link at all (e.g. a recruiter sent only
a PDF attachment, no posting URL); and that the caller should check
for an existing vacancy (e.g. via `find_existing`, passing just
`company` when there is no `source_url` to check against) before
creating, since the tool itself does not deduplicate.

#### Scenario: The tool description states the unknown-role convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it contains the words `unknown` and `needs_review` in a
  sentence describing when to use them together

#### Scenario: The tool description states the synthesized-found_date convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it contains the words `found_date`, `applied_date`, and
  `migrated` in a sentence describing when to synthesize the former
  from the latter and tag the result

#### Scenario: The tool description states the check-before-create convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it states that the tool does not deduplicate and that the
  caller should check for an existing vacancy first

#### Scenario: The tool description states the no-source_url convention
- **WHEN** the `create_vacancy` tool's description is inspected
- **THEN** it states that `source_url` may be omitted when the source
  has no link, naming a PDF-only recruiter message as an example

### Requirement: create_vacancy tool's source_url parameter is optional
Calling the `create_vacancy` tool with no `source_url` argument SHALL
create a vacancy with no `source_url`, exercised end to end through
the tool against a real vault.

#### Scenario: Omitting source_url through the tool creates a vacancy with none
- **WHEN** the `create_vacancy` tool is called with no `source_url`
  argument and otherwise valid arguments
- **THEN** the tool call succeeds and the created vacancy has no
  `source_url`

### Requirement: repeated create_vacancy calls behave predictably as a batch
A sequence of `create_vacancy` tool calls SHALL each independently
succeed or fail without affecting the vault state any other call in
the sequence already committed: a successful call's company directory
and vacancy file persist regardless of a later call's outcome, and a
failing call writes nothing partial.

#### Scenario: Ten sequential creations produce ten vacancies with distinct ids
- **WHEN** the `create_vacancy` tool is called ten times in sequence
  with valid, distinct arguments
- **THEN** ten vacancies exist afterward, each with a distinct id

#### Scenario: A creation failing mid-batch leaves prior creations intact and writes nothing partial
- **GIVEN** a sequence of `create_vacancy` tool calls where the sixth
  call's arguments are invalid (e.g. a non-found status with no
  applied_date)
- **WHEN** all ten calls are made in sequence, in order
- **THEN** the first five calls' vacancies exist unchanged, the sixth
  call's tool result reports a typed error and creates no company
  directory or vacancy file, and the remaining calls proceed
  independently of the sixth's failure

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
