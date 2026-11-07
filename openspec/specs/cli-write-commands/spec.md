# cli-write-commands Specification

## Purpose
TBD - created by openspec-sync-specs during change cli-write. Update Purpose after archive.

## Requirements

### Requirement: every write command exits 0 on success, non-zero on a typed error
Every write command SHALL exit 0 when its underlying `core.py` call
succeeds, and SHALL exit non-zero with a descriptive message when it
raises any typed error. The write commands are `note`, `status set`,
`edit`, `add`, `new`, `reindex`, and `init`.

#### Scenario: A successful write command exits 0
- **WHEN** any write command is run with valid arguments against a
  writable vault
- **THEN** it exits 0

#### Scenario: A typed core error exits non-zero with a message
- **WHEN** any write command is run with arguments that cause its
  underlying `core.py` call to raise a typed error
- **THEN** it exits non-zero and prints a message describing the error

#### Scenario: init exits 0 whether it creates a vault or finds one already initialized
- **WHEN** `vacancy-radar init` is run, whether against a path with
  nothing at that location or against an already-initialized vault
- **THEN** it exits 0 in both cases

#### Scenario: edit exits non-zero on invalid vacancy data
- **WHEN** `vacancy-radar edit <vacancy> --source-url ftp://example.com`
  is run
- **THEN** it exits non-zero, prints a message describing the
  validation failure, and the vacancy is unchanged

### Requirement: an ambiguous vacancy match writes nothing and exits non-zero
`note`, `status set`, `edit`, and `add` SHALL, when the vacancy
argument cannot be narrowed to exactly one vacancy — because
`core.resolve` returned more than one company candidate, or because the
resolved company holds more than one vacancy — print what it matched
and exit non-zero without performing any write.

#### Scenario: An ambiguous query blocks the write
- **GIVEN** a query that resolves to more than one vacancy or company
- **WHEN** `note`, `status set`, `edit`, or `add` is run with that
  query
- **THEN** the command exits non-zero, prints the candidates, and no
  file in the vault is modified

### Requirement: write commands resolve a vacancy by id, company name, or fuzzy match
`note`, `status set`, `edit`, and `add` SHALL accept a vacancy argument
that resolves via `core.resolve_vacancy`: exact vacancy id, exact
company slug, exact company name, or unambiguous fuzzy company name,
with a company-tier match narrowed to that company's single vacancy.
A company holding more than one vacancy, or none, SHALL exit non-zero
without writing.

#### Scenario: A command accepts a vacancy by its exact id
- **WHEN** a write command is given an existing vacancy's exact id
- **THEN** it operates on that vacancy

#### Scenario: A command accepts a vacancy by an unambiguous fuzzy company match
- **WHEN** a write command is given a query that fuzzy-matches exactly
  one company with exactly one vacancy eligible for the operation
- **THEN** it operates on that vacancy

#### Scenario: A command accepts a vacancy by its company's exact display name
- **GIVEN** a company with exactly one vacancy
- **WHEN** a write command is given that company's display name
- **THEN** it operates on that vacancy and exits 0

#### Scenario: A company with several vacancies exits non-zero naming them
- **GIVEN** a company with two vacancies
- **WHEN** a write command is given that company's name
- **THEN** the command exits non-zero, its output names both vacancy
  ids, and no file in the vault is modified

#### Scenario: A company with no vacancies exits non-zero
- **GIVEN** a company directory with no vacancies
- **WHEN** a write command is given that company's name
- **THEN** the command exits non-zero and no file in the vault is
  modified

### Requirement: add --stdin reads content from standard input
`vacancy-radar add` SHALL, when given `--stdin` instead of `--file`,
read the document's content from standard input.

#### Scenario: Piped content is filed via --stdin
- **WHEN** `vacancy-radar add <vacancy> --kind ... --title ... --date
  ... --stdin` is run with content piped to standard input
- **THEN** the created document's content equals what was piped in

### Requirement: --json emits the created path and outcome
Every write command SHALL, when run with `--json`, emit a JSON document
naming the affected path and the outcome of the call (created,
unchanged/no-op, changed, or deduped-existing, as applicable).

#### Scenario: add --json reports the created path
- **WHEN** `vacancy-radar add ... --json` is run and files a new
  document
- **THEN** stdout is valid JSON naming the created document's path

#### Scenario: status set --json reports a no-op outcome
- **WHEN** `vacancy-radar status set <vacancy> <same-status> --json` is
  run
- **THEN** stdout is valid JSON whose outcome indicates no change was
  made

#### Scenario: edit --json reports the changed fields
- **WHEN** `vacancy-radar edit <vacancy> --recruiter "Anna K." --json`
  is run and applies a change
- **THEN** stdout is valid JSON whose outcome indicates a change and
  which names `recruiter` among the changed fields

#### Scenario: edit --json reports a no-op outcome
- **WHEN** `vacancy-radar edit <vacancy> --json` is run with no field
  options
- **THEN** stdout is valid JSON whose outcome indicates no change was
  made

### Requirement: add rejects non-UTF-8 file content with a typed CLI error
The `add` CLI command SHALL, when `--file` names a file that is not
valid UTF-8 text, exit non-zero with a message naming the file and
stating it is not valid text, and SHALL NOT allow an unhandled
exception to propagate out of the command.

#### Scenario: add --file with a PDF exits cleanly, not with a traceback
- **GIVEN** a valid PDF file
- **WHEN** `vacancy-radar add <vacancy> --kind posting --title T --date
  2026-01-01 --file <the PDF's path>` is run
- **THEN** the command exits non-zero, its output names the file and
  states it is not valid text, and no Python traceback appears in its
  output

#### Scenario: the error message names the PDF-attachment workaround
- **WHEN** `add --file` is run against a non-UTF-8 file
- **THEN** the command's error output mentions copying the file into
  the vacancy's `documents/` directory and running `reindex
  --extract-sidecars`

### Requirement: add rejects non-UTF-8 stdin content with the same typed error
The `add` CLI command SHALL, when `--stdin` is given and standard input
does not decode as UTF-8 text, exit non-zero with the same kind of
message `--file` produces for non-UTF-8 content, and SHALL NOT allow an
unhandled exception to propagate out of the command.

#### Scenario: add --stdin with binary input exits cleanly, not with a traceback
- **GIVEN** binary (non-UTF-8) bytes available to pipe as standard
  input
- **WHEN** `vacancy-radar add <vacancy> --kind posting --title T --date
  2026-01-01 --stdin` is run with those bytes piped in
- **THEN** the command exits non-zero, its output states the input is
  not valid text, and no Python traceback appears in its output

### Requirement: add's existing text-content behavior is unaffected by the non-UTF-8 check
`add --file`/`--stdin` SHALL continue to file valid UTF-8 text content
exactly as before this change, for both the default and `--json`
output paths.

#### Scenario: valid UTF-8 --file content is filed unchanged
- **GIVEN** a UTF-8 text file
- **WHEN** `add --file` is run with that file
- **THEN** the command exits 0 and the filed document's content
  matches the file's content, exactly as before this change

### Requirement: edit exposes one option per editable field
`vacancy-radar edit <vacancy>` SHALL expose one option per field
`core.edit_vacancy` accepts — `--source-url`, `--role`, `--stage-note`,
`--salary-note`, `--recruiter`, `--external-id`, `--tags`,
`--found-date`, `--applied-date`, `--resume` — and SHALL expose no
option for `id`, `status`, `company`, or `company_slug`.

#### Scenario: an option given sets that field
- **WHEN** `vacancy-radar edit <vacancy> --recruiter "Anna K."` is run
- **THEN** the command exits 0 and the vacancy's `recruiter` is
  `"Anna K."`

#### Scenario: several options are applied in one invocation
- **WHEN** `vacancy-radar edit <vacancy> --source-url <url>
  --recruiter "Anna K."` is run
- **THEN** the command exits 0 and both fields carry their new values

#### Scenario: no status option is exposed
- **WHEN** `vacancy-radar edit --help` is inspected
- **THEN** it lists no option for setting `status`, `company`, or `id`

#### Scenario: --resume sets the resume
- **WHEN** `vacancy-radar edit <vacancy> --resume backend-v2` is run
- **THEN** the command exits 0 and the vacancy's `resume` is
  `"backend-v2"`

#### Scenario: --clear resume removes it
- **GIVEN** a vacancy with a `resume`
- **WHEN** `vacancy-radar edit <vacancy> --clear resume` is run
- **THEN** the command exits 0 and `resume` is absent from the
  vacancy's frontmatter

### Requirement: edit clears fields via a repeatable --clear option
`edit` SHALL accept a repeatable `--clear FIELD` option naming a
nullable field to remove from the vacancy's frontmatter, and SHALL exit
non-zero with a descriptive message when the named field is not
editable, is not nullable, or is also given as a value option in the
same invocation.

#### Scenario: --clear removes a nullable field
- **GIVEN** a vacancy with a `recruiter`
- **WHEN** `vacancy-radar edit <vacancy> --clear recruiter` is run
- **THEN** the command exits 0 and `recruiter` is absent from the
  vacancy's frontmatter

#### Scenario: --clear repeats for several fields
- **WHEN** `vacancy-radar edit <vacancy> --clear recruiter --clear
  salary-note` is run
- **THEN** the command exits 0 and both fields are absent afterward

#### Scenario: clearing an uneditable field exits non-zero
- **WHEN** `vacancy-radar edit <vacancy> --clear status` is run
- **THEN** the command exits non-zero, its message names `status` and
  lists the editable fields, and nothing is written

#### Scenario: clearing a non-nullable field exits non-zero
- **WHEN** `vacancy-radar edit <vacancy> --clear role` is run
- **THEN** the command exits non-zero with a message naming `role`, and
  nothing is written

#### Scenario: setting and clearing the same field exits non-zero
- **WHEN** `vacancy-radar edit <vacancy> --recruiter "Anna K." --clear
  recruiter` is run
- **THEN** the command exits non-zero with a message naming
  `recruiter`, and nothing is written

### Requirement: edit's date options reject non-ISO values before writing
`--found-date` and `--applied-date` SHALL be parsed with the same ISO
date handling every other date option in the CLI uses, and SHALL exit
non-zero naming the offending option when the value is not an ISO date,
without performing any write.

#### Scenario: a malformed date exits non-zero
- **WHEN** `vacancy-radar edit <vacancy> --found-date 11-08-2026` is
  run
- **THEN** the command exits non-zero, its message names
  `--found-date`, and the vacancy is unchanged

### Requirement: edit --tags replaces the tag list
`--tags` SHALL take a comma-separated list that replaces the vacancy's
existing tags outright, and an empty value SHALL set an empty list.
`--clear tags` SHALL NOT be accepted.

#### Scenario: --tags replaces rather than appends
- **GIVEN** a vacancy tagged `remote,python`
- **WHEN** `vacancy-radar edit <vacancy> --tags "onsite"` is run
- **THEN** the vacancy's tags afterward are exactly `["onsite"]`

#### Scenario: an empty --tags value empties the list
- **WHEN** `vacancy-radar edit <vacancy> --tags ""` is run
- **THEN** the vacancy's tags afterward are an empty list

### Requirement: edit prints what changed on success
`edit` SHALL, without `--json`, print the vacancy id and one line per
changed field naming the field and its old and new values, and SHALL
report a no-op call as unchanged.

#### Scenario: a successful edit names each changed field
- **WHEN** `vacancy-radar edit <vacancy> --recruiter "Anna K."` is run
  and applies a change
- **THEN** its output names the vacancy id, `recruiter`, and both the
  old and new values

#### Scenario: a no-op edit reports unchanged
- **WHEN** `vacancy-radar edit <vacancy>` is run with no field options
- **THEN** the command exits 0 and its output reports that nothing
  changed

### Requirement: status set accepts the resume used
`vacancy-radar status set <vacancy> <status>` SHALL accept an optional
`--resume LABEL` and pass it through to `set_status`.

#### Scenario: applying with --resume records it
- **GIVEN** a vacancy at status `found`
- **WHEN** `vacancy-radar status set <vacancy> applied --applied-date
  2026-10-01 --resume backend-v2` is run
- **THEN** the command exits 0, the vacancy's status is `applied`, and
  its `resume` is `"backend-v2"`

### Requirement: new accepts the resume used
`vacancy-radar new` SHALL accept an optional `--resume LABEL` and pass
it through to `create_vacancy`.

#### Scenario: creating an applied vacancy with --resume records it
- **WHEN** `vacancy-radar new` is run with `--status applied`,
  `--applied-date`, and `--resume backend-v2`
- **THEN** the command exits 0 and the created vacancy's `resume` is
  `"backend-v2"`
