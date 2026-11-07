## MODIFIED Requirements

### Requirement: set_status preserves every other line in vacancy.md
`set_status` SHALL change only the `status` (and, when applicable,
`applied_date`, and `resume` when one is given) frontmatter fields,
the status-history block, and — only when a given `resume` differs
from the stored one — the edit-history block; every other line of
`vacancy.md` — other frontmatter fields, comments, and body content
above those blocks — SHALL be byte-identical before and after the
call.

#### Scenario: A round trip differs only in status and history
- **GIVEN** a vacancy.md file read into text before a `set_status` call
- **WHEN** `set_status` changes that vacancy's status and the file is
  read again
- **THEN** the only differing lines are the `status` field (and
  `applied_date`, if it changed) and the status-history block

#### Scenario: a round trip with a resume also differs in resume and edit history
- **GIVEN** a vacancy.md file read into text before a `set_status` call
- **WHEN** `set_status` changes that vacancy's status and gives a
  `resume` different from the stored one
- **THEN** the only differing lines are `status`, `applied_date` (if
  it changed), `resume`, the status-history block, and the
  edit-history block
