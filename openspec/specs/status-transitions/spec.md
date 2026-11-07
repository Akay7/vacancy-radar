# status-transitions Specification

## Purpose
TBD - created by openspec-sync-specs during change cli-write. Update Purpose after archive.

## Requirements

### Requirement: the permitted status graph is data in models.py
`models.py` SHALL define the permitted status-transition graph
(`STATUS_TRANSITIONS`) as module-level data — a mapping from each
`Status` to the set of statuses reachable from it without `force` — not
as conditional branches inside `set_status`.

#### Scenario: The transition graph is inspectable without calling set_status
- **WHEN** `models.STATUS_TRANSITIONS` is read directly
- **THEN** it names, for every `Status`, the set of statuses reachable
  from it without `force`, independent of any `set_status` call

### Requirement: a permitted forward transition succeeds
`set_status(vacancy_id, new_status, ...)` SHALL, when `new_status` is
reachable from the vacancy's current status per `STATUS_TRANSITIONS`,
update the vacancy's frontmatter `status` field and return a
`StatusChange` reflecting the change, without requiring `force`.

#### Scenario: applied to screening succeeds without force
- **GIVEN** a vacancy currently at status `applied`
- **WHEN** `set_status` is called with `new_status="screening"`
- **THEN** the vacancy's stored status becomes `screening` and the
  returned `StatusChange` reports the transition

### Requirement: a backward transition without force raises, naming both statuses
`set_status` SHALL raise a typed error identifying the current status
and the requested status when `new_status` is not reachable from the
current status per `STATUS_TRANSITIONS` and `force` is not set. The
vacancy's frontmatter SHALL be unchanged.

#### Scenario: interview back to applied without force raises
- **GIVEN** a vacancy currently at status `interview`
- **WHEN** `set_status` is called with `new_status="applied"` and
  `force` not set
- **THEN** a typed error is raised naming both `interview` and
  `applied`, and the vacancy's stored status is still `interview`

### Requirement: a backward transition with force succeeds
`set_status` SHALL, when `force=True`, apply any transition regardless
of `STATUS_TRANSITIONS`.

#### Scenario: interview back to applied with force succeeds
- **GIVEN** a vacancy currently at status `interview`
- **WHEN** `set_status` is called with `new_status="applied"` and
  `force=True`
- **THEN** the vacancy's stored status becomes `applied`

### Requirement: a transition to the same status is a no-op
`set_status` SHALL, when `new_status` equals the vacancy's current
status, make no change to the vault and return a `StatusChange`
indicating nothing changed, regardless of `force`.

#### Scenario: Setting the current status again changes nothing
- **GIVEN** a vacancy currently at status `screening`
- **WHEN** `set_status` is called with `new_status="screening"`
- **THEN** no file in the vault is modified and the returned
  `StatusChange` reports no change

### Requirement: an invalid status string raises, listing permitted values
`set_status` SHALL raise a typed error naming every permitted `Status`
value when `new_status` is not one of them.

#### Scenario: A misspelled status name raises with the valid list
- **WHEN** `set_status` is called with `new_status="intervew"`
- **THEN** a typed error is raised whose message lists every valid
  `Status` value, and no file in the vault is modified

### Requirement: set_status appends to status history and preserves prior entries
`set_status` SHALL append one dated entry to a status-history block in
`vacancy.md`'s body on every status-changing call, and SHALL preserve
every entry a prior call wrote.

#### Scenario: A second status change preserves the first entry
- **GIVEN** a vacancy that has already had one status change recorded
  in its status-history block
- **WHEN** `set_status` changes its status again
- **THEN** the status-history block contains both the original entry
  and the new one

### Requirement: set_status never modifies stage_note
`set_status` SHALL NOT write to the vacancy's `stage_note` frontmatter
field under any circumstance.

#### Scenario: stage_note is unchanged after a status change
- **GIVEN** a vacancy with a non-empty `stage_note`
- **WHEN** `set_status` changes that vacancy's status
- **THEN** `stage_note` afterward is byte-identical to its value before
  the call

### Requirement: moving off found requires applied_date
`set_status` SHALL, when the transition moves the vacancy off `found`
and it has no `applied_date` yet, require an `applied_date` argument
and raise a typed error naming the vacancy when one is not given.

#### Scenario: found to applied without applied_date raises
- **GIVEN** a vacancy currently at status `found` (and so with no
  `applied_date`)
- **WHEN** `set_status` is called with `new_status="applied"` and no
  `applied_date`
- **THEN** a typed error is raised and the vacancy's stored status is
  still `found`

#### Scenario: found to applied with applied_date succeeds
- **GIVEN** a vacancy currently at status `found`
- **WHEN** `set_status` is called with `new_status="applied"` and an
  explicit `applied_date`
- **THEN** the vacancy's stored status becomes `applied` and its stored
  `applied_date` equals the value given

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

### Requirement: a status change updates document rows' status without re-embedding them
`set_status` SHALL leave that vacancy's document rows in the index
carrying the new status, with their stored vectors unchanged from
before the call.

#### Scenario: Document vectors are untouched by a status change
- **GIVEN** a vacancy with at least one indexed document, and that
  document's vector recorded before a `set_status` call
- **WHEN** `set_status` changes that vacancy's status
- **THEN** the document's row reports the new status and its vector is
  identical to the one recorded before the call
