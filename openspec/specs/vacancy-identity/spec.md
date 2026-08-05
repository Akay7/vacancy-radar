# vacancy-identity Specification

## Purpose
TBD - created by archiving change vault-model. Update Purpose after archive.

## Requirements

### Requirement: slugify produces readable ascii, never hex escapes
`slugify` SHALL transliterate non-ascii input into readable ascii text
(never percent-encoding or hex escapes), lowercase it, and collapse
punctuation and whitespace into single hyphens.

#### Scenario: transliteration produces readable ascii
- **GIVEN** the placeholder inputs `"Ромашка"`, `"Widget & Sons"`,
  `"Acme Inc."`, and `"Šaltinis Studija"`
- **WHEN** each is passed to `slugify`
- **THEN** each result is a readable, lowercase ascii slug (e.g.
  `"romashka"` for `"Ромашка"`, `"saltinis-studija"` for
  `"Šaltinis Studija"`)
- **THEN** no result contains a percent-encoded or hex-escaped
  character

### Requirement: new_vacancy_id is deterministic
`new_vacancy_id` SHALL return the same id for the same
`(found_date, company_slug, role, existing_ids)` inputs every time it
is called, and SHALL NOT mutate the `existing_ids` set it is given.

#### Scenario: same inputs produce the same id
- **GIVEN** a fixed `found_date`, `company_slug`, `role`, and
  `existing_ids` set
- **WHEN** `new_vacancy_id` is called twice with those exact inputs
- **THEN** both calls return the same id
- **THEN** the `existing_ids` set passed in is unchanged after both
  calls

### Requirement: Ids begin with an ISO date so lexical sort is chronological
`new_vacancy_id` SHALL format ids as
`{YYYY-MM-DD}-{company_slug}-{role_slug}`, with all three segments
always present, so that sorting ids lexically produces the same order
as sorting by `found_date`.

#### Scenario: id format and lexical-equals-chronological sort
- **GIVEN** several `(found_date, company_slug, role)` triples with
  distinct dates
- **WHEN** an id is minted for each and the ids are sorted lexically
- **THEN** each id starts with its `found_date` in `YYYY-MM-DD` form
  followed by its `company_slug` and role slug
- **THEN** the lexical order of the ids matches the chronological order
  of their `found_date` values

### Requirement: Ids come from frontmatter content only, never from a path
A vacancy's `id` SHALL be determined entirely by its frontmatter
content. Neither `new_vacancy_id` nor `Vacancy` parsing SHALL accept or
derive an id from a file path, so an id stays stable if the file or its
containing directory is renamed.

#### Scenario: identical frontmatter yields identical id regardless of location
- **GIVEN** the same frontmatter content, representing a file that
  could exist at two different paths (e.g. before and after a
  directory rename)
- **WHEN** a `Vacancy` is constructed from that frontmatter content
  each time
- **THEN** the resulting `id` is identical both times, since parsing
  takes no path input

### Requirement: Id collisions resolve deterministically with a numeric suffix
`new_vacancy_id` SHALL append a numeric suffix (`-2`, `-3`, ...) —
choosing the lowest unused suffix, deterministically — when its
computed `{date}-{company_slug}-{role_slug}` is already present in
`existing_ids`.

#### Scenario: a batch of same-day, same-company, unknown-role vacancies collide and resolve
- **GIVEN** a migration-shaped batch of several vacancies sharing the
  same `found_date` and `company_slug`, all with `role` set to
  `UNKNOWN_ROLE`
- **WHEN** an id is minted for each in sequence, adding each returned
  id to `existing_ids` before minting the next
- **THEN** the first gets the unsuffixed
  `{date}-{company_slug}-{role_slug}` id
- **THEN** each subsequent vacancy gets the next unused numeric suffix
  (`-2`, `-3`, ...), in order
- **THEN** every id in the batch is unique

### Requirement: Role slugs truncate to a bounded, deterministic length
The role portion of a minted id SHALL be truncated to a fixed maximum
length by plain truncation (not word-boundary-aware), so ids stay
filesystem-safe and truncation output is deterministic.

#### Scenario: long role names truncate deterministically
- **GIVEN** a `role` whose slug form exceeds the maximum role-slug
  length
- **WHEN** an id is minted for it
- **THEN** the role segment of the id is truncated to the maximum
  length
- **THEN** minting an id for the same over-length role again produces
  the identical truncated segment
</content>
