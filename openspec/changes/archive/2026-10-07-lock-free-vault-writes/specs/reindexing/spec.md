## ADDED Requirements

### Requirement: an explicit reindex surfaces failures; a post-write refresh is best-effort
A direct `reindex()` call (and `vacancy-radar reindex`) SHALL raise
when the index build fails, including on a concurrency conflict with
another writer, after the same bounded retry the post-write refresh
uses. The refresh a write function performs as its last step SHALL
instead follow `concurrent-writes`' best-effort rule: a conflict that
persists after retries is logged, not raised.

#### Scenario: An explicit reindex reports a persistent conflict
- **GIVEN** the index build is made to fail with a concurrency
  conflict on every attempt
- **WHEN** `reindex()` is called directly
- **THEN** it raises after its retries, rather than returning a report

#### Scenario: A transient conflict is retried transparently
- **GIVEN** the index build fails with a concurrency conflict on its
  first attempt only
- **WHEN** `reindex()` is called directly
- **THEN** it returns an `IndexReport` without raising
