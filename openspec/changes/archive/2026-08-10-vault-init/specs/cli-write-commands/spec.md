## MODIFIED Requirements

### Requirement: every write command exits 0 on success, non-zero on a typed error
Each of `note`, `status set`, `add`, `new`, `reindex`, and `init` SHALL
exit 0 when its underlying `core.py` call succeeds, and SHALL exit
non-zero with a descriptive message when it raises any typed error.

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
