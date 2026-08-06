# vacancy-listing Specification

## Purpose
TBD - created by openspec-sync-specs during change retrieval. Update Purpose after archive.

## Requirements

### Requirement: list_vacancies returns all vacancies up to limit with no filters
`list_vacancies()` called with no filters SHALL return every vacancy
in the vault as `VacancySummary` rows, truncated to `limit` (default
50).

#### Scenario: No filters returns all vacancies up to limit
- **WHEN** `list_vacancies` is called with no filter arguments against
  a vault with fewer vacancies than the default limit
- **THEN** every vacancy in the vault appears exactly once in the
  result

### Requirement: status filters accept several values and return their union
`list_vacancies(status=[...])` SHALL return the union of vacancies
matching any of the given statuses.

#### Scenario: status accepts several values and returns their union
- **WHEN** `list_vacancies` is called with `status` naming two
  statuses
- **THEN** the result contains every vacancy whose status is either of
  the two, and no vacancy whose status is neither

### Requirement: company filter restricts to one company
`list_vacancies(company=...)` SHALL restrict results to vacancies
belonging to the resolved company.

#### Scenario: company restricts to that company
- **WHEN** `list_vacancies` is called with `company` naming one
  company
- **THEN** every returned vacancy belongs to that company and no
  vacancy from another company is returned

### Requirement: since excludes vacancies applied before the given date
`list_vacancies(since=...)` SHALL exclude vacancies whose
`applied_date` is earlier than `since`.

#### Scenario: since excludes vacancies applied earlier
- **WHEN** `list_vacancies` is called with `since` set to a date after
  some vacancies' `applied_date`
- **THEN** those earlier-applied vacancies are absent from the result

### Requirement: needs_review returns exactly the tagged vacancies
`list_vacancies(needs_review=True)` SHALL return exactly the
vacancies tagged `needs_review`, and no others.

#### Scenario: needs_review returns exactly the vacancies tagged needs_review
- **WHEN** `list_vacancies` is called with `needs_review=True`
- **THEN** the result is exactly the set of vacancies whose `tags`
  includes `needs_review`

### Requirement: stale_days filters on last_activity, not applied_date
`list_vacancies(stale_days=...)` SHALL include a vacancy only when its
`last_activity` (the vault's most-recent-document-or-fallback date, as
defined by `VaultSnapshot.last_activity`) is at least `stale_days` in
the past — independent of how long ago `applied_date` was.

#### Scenario: An application from long ago with a recent document is not stale
- **WHEN** `list_vacancies` is called with `stale_days` set such that a
  vacancy applied well outside that window has a document dated within
  the window
- **THEN** that vacancy is excluded from the stale result

#### Scenario: A vacancy with no activity since applying is stale
- **WHEN** `list_vacancies` is called with `stale_days` set such that a
  vacancy's `last_activity` falls outside that window, with no
  documents newer than `applied_date`
- **THEN** that vacancy is included in the stale result

### Requirement: sort='activity' orders by last_activity descending, stable for ties
`list_vacancies(sort='activity')` SHALL order results by
`last_activity` descending, breaking ties deterministically (by
vacancy `id` ascending) so repeated calls over unchanged data return
the same order.

#### Scenario: sort='activity' orders by last_activity descending, stable for ties
- **WHEN** `list_vacancies` is called with `sort='activity'` against a
  vault containing two vacancies with the same `last_activity`
- **THEN** results are ordered by `last_activity` descending, and the
  two tied vacancies appear in the same relative order on every call

### Requirement: summaries contain no document bodies
Every `VacancySummary` SHALL contain only `id`, `company`, `role`,
`status`, `applied_date`, `last_activity`, and `document_count` — no
document text or path.

#### Scenario: Summaries contain no document bodies
- **WHEN** `list_vacancies` is called against a vault containing
  vacancies with documents
- **THEN** no returned `VacancySummary` contains a document body or
  document path
