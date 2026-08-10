# mcp-write-tools

## Purpose
Defines the MCP server's three write tools — `append_note`, `set_status`,
`add_document` — each a thin delegation to a single `core.py` call, with
schemas mirroring `core.py`'s own parameter names and `models.py`-derived
enums, and with safety guarantees: no delete, no overwrite (beyond
`set_status`'s in-place frontmatter update), and no caller-supplied
filesystem path.

## Requirements

### Requirement: each write tool delegates to exactly one core.py function
`append_note`, `set_status`, and `add_document` SHALL each, with
`core.py` mocked, call exactly one `core.py` function and return that
call's result unmodified apart from serialization. Neither the tool
module nor any tool handler SHALL contain filtering, sorting, path
manipulation, or other business rules of its own.

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
  `{vacancy_id, new_status, note, applied_date, force}`, matching
  `core.set_status`'s own parameter names exactly

### Requirement: every write tool exposes a valid JSON schema
Each of the three write tools SHALL declare an `inputSchema` that is
valid JSON Schema, listed in the server's `tools/list` response.

#### Scenario: every write tool's schema validates as JSON Schema
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of `append_note`, `set_status`, `add_document` is
  present, and each one's `inputSchema` validates successfully against
  the JSON Schema meta-schema

### Requirement: enum-typed write tool parameters enumerate permitted values from models.py
An enum-typed write tool parameter SHALL declare its permitted values
from `models.py`: `set_status`'s `new_status` from `Status`,
`add_document`'s `kind` from `DocumentKind` — never a literal list
written into the server module.

#### Scenario: add_document tool's kind enum matches DocumentKind's members
- **WHEN** the `add_document` tool's schema is inspected
- **THEN** its `kind` parameter's `enum` values equal
  `[k.value for k in DocumentKind]` exactly

#### Scenario: set_status tool's new_status enum matches Status's members
- **WHEN** the `set_status` tool's schema is inspected
- **THEN** its `new_status` parameter's `enum` values equal
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

### Requirement: an out-of-range write tool argument returns a typed error, not a raised exception
A write tool call SHALL, when an argument is outside its declared enum
or `core.py` rejects it for another typed reason (an invalid
transition, a nonexistent vacancy), produce a tool result reporting the
typed error rather than raising an unhandled exception out of the tool
handler.

#### Scenario: set_status with an unreachable transition returns a typed error result
- **GIVEN** `core.set_status` is mocked to raise
  `core.InvalidStatusTransitionError`
- **WHEN** the `set_status` tool is called with a backward transition
  and no `force` argument
- **THEN** the tool call returns without raising, and the tool result
  reports an error naming `InvalidStatusTransitionError`

### Requirement: the three write tools carry readOnlyHint false and destructiveHint false
`append_note`, `set_status`, and `add_document` SHALL each declare
`annotations.readOnlyHint = false` and
`annotations.destructiveHint = false`.

#### Scenario: every write tool's annotations report readOnlyHint false and destructiveHint false
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of the three write tools' `annotations.readOnlyHint` is
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
overwrite an existing document or note file. `set_status`'s in-place
`vacancy.md` frontmatter update is the sole exception, and it SHALL
preserve the file's body content outside the fields it changes.

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
