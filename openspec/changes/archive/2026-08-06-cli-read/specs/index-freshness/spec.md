## ADDED Requirements

### Requirement: staleness detection names the count of vault documents missing from the index
The index-freshness check SHALL compare the vault's current document
set (a fresh `read_vault` call) against what the index table actually
holds, and, when the index is missing documents the vault has,
produce a warning naming how many are missing.

#### Scenario: search against a stale index returns results plus a staleness warning naming the count
- **GIVEN** an index that was built before documents were added to the
  vault
- **WHEN** the freshness check runs against that vault and index
- **THEN** it reports a warning naming the number of vault documents
  absent from the index

### Requirement: staleness degrades, it never blocks
The index-freshness check SHALL never raise. A stale index is always
reported as a warning attached to a successful result, never as an
exception that prevents the caller from getting an answer.

#### Scenario: A stale index degrades a caller, it does not block it
- **GIVEN** an index that is missing documents present in the vault
- **WHEN** the freshness check runs
- **THEN** no exception is raised and the caller receives both its
  normal result and the staleness warning
