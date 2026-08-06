# cli-write-commands Specification

## Purpose
TBD - created by openspec-sync-specs during change cli-write. Update Purpose after archive.

## Requirements

### Requirement: every write command exits 0 on success, non-zero on a typed error
Each of `note`, `status set`, `add`, `new`, and `reindex` SHALL exit 0
when its underlying `core.py` call succeeds, and SHALL exit non-zero
with a descriptive message when it raises any typed error.

#### Scenario: A successful write command exits 0
- **WHEN** any write command is run with valid arguments against a
  writable vault
- **THEN** it exits 0

#### Scenario: A typed core error exits non-zero with a message
- **WHEN** any write command is run with arguments that cause its
  underlying `core.py` call to raise a typed error
- **THEN** it exits non-zero and prints a message describing the error

### Requirement: an ambiguous vacancy match writes nothing and exits non-zero
`note`, `status set`, and `add` SHALL, when `core.resolve` returns more
than one candidate for the vacancy argument, print the candidates and
exit non-zero without performing any write.

#### Scenario: An ambiguous query blocks the write
- **GIVEN** a query that resolves to more than one vacancy or company
- **WHEN** `note`, `status set`, or `add` is run with that query
- **THEN** the command exits non-zero, prints the candidates, and no
  file in the vault is modified

### Requirement: write commands resolve a vacancy by id, company name, or fuzzy match
`note`, `status set`, and `add` SHALL accept a vacancy argument that
resolves via `core.resolve`'s full tier order: exact vacancy id, exact
company slug, exact company name, or unambiguous fuzzy company name.

#### Scenario: A command accepts a vacancy by its exact id
- **WHEN** a write command is given an existing vacancy's exact id
- **THEN** it operates on that vacancy

#### Scenario: A command accepts a vacancy by an unambiguous fuzzy company match
- **WHEN** a write command is given a query that fuzzy-matches exactly
  one company with exactly one vacancy eligible for the operation
- **THEN** it operates on that vacancy

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
unchanged/no-op, or deduped-existing, as applicable).

#### Scenario: add --json reports the created path
- **WHEN** `vacancy-radar add ... --json` is run and files a new
  document
- **THEN** stdout is valid JSON naming the created document's path

#### Scenario: status set --json reports a no-op outcome
- **WHEN** `vacancy-radar status set <vacancy> <same-status> --json` is
  run
- **THEN** stdout is valid JSON whose outcome indicates no change was
  made
