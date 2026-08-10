## ADDED Requirements

### Requirement: every applied edit appends one dated entry per changed field
An applied `edit_vacancy` call SHALL append, under a `## Edit History`
heading in `vacancy.md`'s body, one entry per field whose value
changed, in the form `- <ISO date>: <field>: <old> -> <new>`. Fields
given values equal to what is stored SHALL contribute no entry.

#### Scenario: a single-field edit appends one entry
- **WHEN** `edit_vacancy` changes a vacancy's `source_url`
- **THEN** the body contains a `## Edit History` block with one entry
  naming `source_url`, today's date, the old URL, and the new URL

#### Scenario: a multi-field edit appends one entry per changed field
- **WHEN** `edit_vacancy` changes `source_url` and `recruiter` in one
  call, while also passing a `salary_note` equal to the stored one
- **THEN** the edit-history block gains exactly two entries, naming
  `source_url` and `recruiter`, and none naming `salary_note`

### Requirement: absent values render as a placeholder rather than an empty string
An entry SHALL render an absent old or new value as `(none)`, so
setting a previously unset field and clearing a set field are both
legible.

#### Scenario: setting a previously absent field
- **GIVEN** a vacancy with no `recruiter`
- **WHEN** `edit_vacancy` sets `recruiter` to `"Anna K."`
- **THEN** the appended entry reads `recruiter: (none) -> Anna K.`

#### Scenario: clearing a set field
- **GIVEN** a vacancy whose `recruiter` is `"Anna K."`
- **WHEN** `edit_vacancy` clears `recruiter`
- **THEN** the appended entry reads `recruiter: Anna K. -> (none)`

### Requirement: an entry is always exactly one line
An entry SHALL occupy exactly one line regardless of the edited value's
content. A value containing newlines SHALL be summarized rather than
embedded verbatim, so no value can introduce what reads as an
additional history entry.

#### Scenario: a multi-line stage_note produces one line
- **WHEN** `edit_vacancy` sets a `stage_note` containing newlines
- **THEN** the appended edit-history entry is a single line, and the
  edit-history block's entry count increases by exactly one

#### Scenario: a value that looks like a history entry does not forge one
- **WHEN** `edit_vacancy` sets a field to a value containing a newline
  followed by text shaped like an entry
- **THEN** the edit-history block's entry count increases by exactly
  one

### Requirement: prior edit-history entries are preserved
Appending an entry SHALL preserve every entry a prior call wrote, in
its original order.

#### Scenario: a second edit preserves the first entry
- **GIVEN** a vacancy that already has one edit-history entry
- **WHEN** `edit_vacancy` changes another field
- **THEN** the edit-history block contains both entries, the original
  first

### Requirement: a missing Edit History block is created at the end of the body
The first applied edit SHALL create a `## Edit History` block at the
end of the body when `vacancy.md`'s body has no such heading yet,
leaving all preceding body content byte-identical.

#### Scenario: the first edit creates the block
- **GIVEN** a vacancy whose body has no edit-history block
- **WHEN** `edit_vacancy` applies a change
- **THEN** the body gains a `## Edit History` heading at its end,
  followed by the new entry, and every preceding line is unchanged

### Requirement: status history and edit history are appended to their own blocks
Both history blocks SHALL be appended section-aware: an entry SHALL be
inserted at the end of its own block — the lines between its heading
and the next `##` heading or the end of the body — never at the end of
the file when another block follows. `set_status` SHALL keep appending
only to `## Status History` and `edit_vacancy` only to `## Edit
History`, whichever order the two blocks appear in.

#### Scenario: a status change after an edit lands in the status block
- **GIVEN** a vacancy whose body carries a `## Status History` block
  followed by a `## Edit History` block
- **WHEN** `set_status` changes that vacancy's status
- **THEN** the new status entry is the last line of the
  `## Status History` block, and the `## Edit History` block's
  contents are unchanged

#### Scenario: an edit after a status change lands in the edit block
- **GIVEN** a vacancy whose body carries both blocks
- **WHEN** `edit_vacancy` applies a change
- **THEN** the new entry is the last line of the `## Edit History`
  block, and the `## Status History` block's contents are unchanged

#### Scenario: status history output is unchanged when it is the last block
- **GIVEN** a vacancy whose body's last section is `## Status History`
- **WHEN** `set_status` changes that vacancy's status
- **THEN** the resulting file is byte-identical to what the prior
  end-of-body append produced for the same inputs

### Requirement: a no-op edit appends nothing
A no-op `edit_vacancy` call SHALL append no edit-history entry and
SHALL NOT create the block.

#### Scenario: a no-op leaves the body untouched
- **GIVEN** a vacancy whose body has no edit-history block
- **WHEN** `edit_vacancy` is called with values equal to what is stored
- **THEN** no `## Edit History` heading is created and the body is
  byte-identical
