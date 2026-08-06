## ADDED Requirements

### Requirement: append_note never overwrites an existing note
`append_note(vacancy_id, text, date=None)` SHALL write a new file for
every call and SHALL NOT modify or truncate any file that already
exists in that vacancy's `documents/` directory.

#### Scenario: A second note on an existing vacancy creates a new file, leaving the first byte-identical
- **GIVEN** a vacancy with one existing note file
- **WHEN** `append_note` is called again for that vacancy
- **THEN** a new file is created and the original note's bytes are
  unchanged

#### Scenario: Two notes on the same date produce two distinct files
- **GIVEN** a vacancy with no notes yet
- **WHEN** `append_note` is called twice for that vacancy with the same
  explicit `date`
- **THEN** two separate files exist afterward and neither call
  overwrote the other's file

### Requirement: append_note's document is searchable without a separate reindex
`append_note` SHALL refresh the index for the document it creates
before returning, so the note is retrievable by `search` in the same
process without an explicit `reindex` call.

#### Scenario: A note is retrievable by search immediately after append_note
- **WHEN** `append_note` is called and returns successfully
- **THEN** a `search` call in the same process against text from that
  note returns it as a hit, without any intervening `reindex` call

### Requirement: append_note's filename is derived, not caller-supplied
`append_note` SHALL derive its file's name from the vacancy, the note's
kind, and its effective date — `append_note`'s signature accepts no
filename or path argument.

#### Scenario: append_note's caller cannot influence the resulting path
- **WHEN** `append_note` is called with only `vacancy_id`, `text`, and
  optionally `date`
- **THEN** the returned path lies inside that vacancy's `documents/`
  directory and its name is fully determined by the vacancy, the note
  kind, and the date used
