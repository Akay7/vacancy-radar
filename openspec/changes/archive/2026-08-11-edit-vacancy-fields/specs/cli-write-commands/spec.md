## MODIFIED Requirements

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
`note`, `status set`, `edit`, and `add` SHALL, when `core.resolve`
returns more than one candidate for the vacancy argument, print the
candidates and exit non-zero without performing any write.

#### Scenario: An ambiguous query blocks the write
- **GIVEN** a query that resolves to more than one vacancy or company
- **WHEN** `note`, `status set`, `edit`, or `add` is run with that
  query
- **THEN** the command exits non-zero, prints the candidates, and no
  file in the vault is modified

### Requirement: write commands resolve a vacancy by id, company name, or fuzzy match
`note`, `status set`, `edit`, and `add` SHALL accept a vacancy argument
that resolves via `core.resolve`'s full tier order: exact vacancy id,
exact company slug, exact company name, or unambiguous fuzzy company
name.

#### Scenario: A command accepts a vacancy by its exact id
- **WHEN** a write command is given an existing vacancy's exact id
- **THEN** it operates on that vacancy

#### Scenario: A command accepts a vacancy by an unambiguous fuzzy company match
- **WHEN** a write command is given a query that fuzzy-matches exactly
  one company with exactly one vacancy eligible for the operation
- **THEN** it operates on that vacancy

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

## ADDED Requirements

### Requirement: edit exposes one option per editable field
`vacancy-radar edit <vacancy>` SHALL expose one option per field
`core.edit_vacancy` accepts — `--source-url`, `--role`, `--stage-note`,
`--salary-note`, `--recruiter`, `--external-id`, `--tags`,
`--found-date`, `--applied-date` — and SHALL expose no option for
`id`, `status`, `company`, or `company_slug`.

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
