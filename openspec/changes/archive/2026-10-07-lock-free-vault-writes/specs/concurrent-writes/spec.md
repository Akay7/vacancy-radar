## Purpose

Defines what vault writes guarantee when several are issued at once —
from threads of one MCP server, from several MCP server processes, or
from the CLI alongside them — without any lock serializing them.

## ADDED Requirements

### Requirement: writes are not serialized by a lock
Write functions (`append_note`, `add_document`, `set_status`,
`edit_vacancy`, `create_vacancy`) and `reindex` SHALL NOT acquire any
in-process or cross-process lock, and SHALL NOT create lock files
inside or outside the vault. A write that is slow (e.g. embedding
during its index refresh) SHALL NOT block another write or a read from
starting.

#### Scenario: A long write does not delay a concurrent write
- **GIVEN** a write whose index refresh is artificially held open
- **WHEN** a second write targeting a different vacancy is started in
  another thread of the same process
- **THEN** the second write's file appears on disk before the first
  write returns

#### Scenario: No lock file is created
- **WHEN** any write function completes
- **THEN** no lock file for the vault exists in the vault or in the
  system temp directory

### Requirement: concurrent creates never overwrite each other
When two or more writers concurrently create a file at the same
derived path — a document or note filename, a vacancy id, or a
company's `_company.md` — exactly one SHALL create that path, and no
writer SHALL replace a file another writer created. A losing
`add_document`/`append_note` SHALL file its content under the next
collision-suffixed filename; a losing `create_vacancy` SHALL mint the
next distinct vacancy id; a losing `_company.md` creation SHALL leave
the winner's file in place and proceed as if the company already
existed.

#### Scenario: Parallel notes on the same day all survive
- **GIVEN** a vacancy with no notes
- **WHEN** eight `append_note` calls with distinct texts and the same
  date run concurrently
- **THEN** eight distinct note files exist afterward, each containing
  exactly one of the eight texts, and every call returned the path of
  the file holding its own text

#### Scenario: Parallel creates of the same vacancy get distinct ids
- **WHEN** four `create_vacancy` calls with the same company, role, and
  `found_date` run concurrently against a company with no directory
- **THEN** four vacancies with distinct ids exist afterward, exactly
  one `_company.md` exists for the company, and every call returned
  successfully

### Requirement: external_id dedupe is exact sequentially and never destructive concurrently
`add_document`'s `external_id` dedupe SHALL remain exact for calls
that do not overlap in time. For calls that overlap, the vault MAY end
with more than one document carrying the same `external_id` under the
vacancy, but no call SHALL overwrite or delete any document, and every
call SHALL return the path of a document carrying that `external_id`.
Once the calls have returned, any further call with that `external_id`
SHALL dedupe to an existing document rather than file another one.

#### Scenario: Racing re-files of one source lose nothing
- **WHEN** four `add_document` calls for the same vacancy with the
  same `external_id` run concurrently
- **THEN** between one and four documents with that `external_id`
  exist afterward, each call returned the path of one of them, and
  every one of those files is intact

#### Scenario: A later re-file dedupes after the race
- **GIVEN** the vault state after the racing re-files above
- **WHEN** `add_document` is called once more with that `external_id`
- **THEN** it returns an existing document's path and creates no file

### Requirement: a vacancy.md changed by another writer is not overwritten silently
`set_status` and `edit_vacancy` SHALL detect that `vacancy.md` changed
between reading it and writing it, and in that case SHALL write
nothing and raise a typed concurrent-modification error naming the
vacancy, leaving the file as the other writer left it. The caller may
retry the call. The only lost-update exposure permitted is a change
landing between this final check and the atomic replace itself.

#### Scenario: A concurrent change makes the second writer fail cleanly
- **GIVEN** a vacancy in status `found`
- **WHEN** another writer edits its `vacancy.md` after
  `set_status(..., "applied", applied_date=...)` has read the file but
  before it writes
- **THEN** `set_status` raises the concurrent-modification error, and
  the file's bytes equal what the other writer wrote

#### Scenario: Retrying after the error applies the change
- **GIVEN** the state after the scenario above
- **WHEN** the same `set_status` call is made again with no other
  writer active
- **THEN** it succeeds and the file has both the other writer's change
  and the new status

### Requirement: a write never fails because its index refresh contended
A write function's file change SHALL be durable once written,
regardless of what happens during the index refresh that follows. When
that refresh fails because another writer is updating the index
concurrently, the write SHALL retry the refresh a bounded number of
times; if it still fails, the write SHALL return its normal result and
log a warning naming the vault. In that case the "searchable/listed
without a separate reindex" guarantees of `note-taking`,
`vacancy-creation`, `vacancy-editing`, `status-transitions`, and
`mcp-write-tools` do not hold for that write until the next successful
reindex, and `search` SHALL report the gap through its existing
staleness warning. Failures of the refresh that are not concurrency
conflicts SHALL propagate as before.

#### Scenario: Index contention does not fail the write
- **GIVEN** the index refresh is made to fail with a concurrency
  conflict on every attempt
- **WHEN** `append_note` is called
- **THEN** the call returns the new note's path, the note file exists,
  a warning is logged, and a subsequent `search` reports the index as
  stale

#### Scenario: The index converges after concurrent writes
- **WHEN** eight writes across different vacancies run concurrently and
  all return, and `reindex()` is then called once
- **THEN** a `search` for text from each write returns it as a hit, and
  no staleness warning is reported

### Requirement: reads are unaffected by concurrent writes
Read functions SHALL never observe a partially written vault file, and
SHALL NOT fail because a write is in progress.

#### Scenario: Reading during a burst of writes
- **WHEN** `list_vacancies` and `get_vacancy` are called repeatedly
  while concurrent writes are running
- **THEN** every read call returns without error and every file it
  reports parses as valid frontmatter
