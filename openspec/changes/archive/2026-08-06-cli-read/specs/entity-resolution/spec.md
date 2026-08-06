## ADDED Requirements

### Requirement: resolve matches an exact vacancy id first
`resolve(query)` SHALL, when `query` equals a vacancy's `id` exactly,
return a `Resolution` naming that vacancy and no others, without
evaluating any lower-priority tier.

#### Scenario: An exact id resolves to that vacancy
- **WHEN** `resolve` is called with a string equal to an existing
  vacancy's `id`
- **THEN** the returned `Resolution` identifies exactly that vacancy
  and `candidates` is empty

### Requirement: resolve matches an exact company slug
`resolve(query)` SHALL, when no vacancy id matched and `query` equals
a `company_slug` exactly, return a `Resolution` naming that company.

#### Scenario: An exact company_slug resolves to that company
- **WHEN** `resolve` is called with a string equal to an existing
  `company_slug`
- **THEN** the returned `Resolution` identifies exactly that company

### Requirement: resolve matches a company display name case-insensitively
`resolve(query)` SHALL, when no id or slug tier matched, resolve a
query that differs from a company's display name only in case to that
company.

#### Scenario: A display name differing only in case resolves
- **WHEN** `resolve` is called with a company's display name in a
  different case (e.g. all-uppercase)
- **THEN** the returned `Resolution` identifies that company

### Requirement: resolve fuzzy-matches an unambiguous partial name
`resolve(query)` SHALL, when no earlier tier matched exactly one
result, fall back to fuzzy matching against company display names
(via the standard library, without a new dependency) and resolve when
exactly one company is a close match.

#### Scenario: "Acme" resolves to acme-corp when unambiguous
- **WHEN** `resolve` is called with `"Acme"` and exactly one company's
  display name is a close match
- **THEN** the returned `Resolution` identifies that company

### Requirement: resolve returns candidates instead of guessing between ambiguous matches
`resolve(query)` SHALL, when any tier (case-insensitive or fuzzy)
matches more than one company, return a `Resolution` whose
`candidates` lists every match and whose resolved entity is absent —
never guess.

#### Scenario: A query matching two companies returns both as candidates and resolves to neither
- **WHEN** `resolve` is called with a query that matches two distinct
  companies at the same tier
- **THEN** the returned `Resolution` has no resolved entity and
  `candidates` contains both companies

### Requirement: resolve returns an empty resolution for no match
`resolve(query)` SHALL, when no tier matches anything, return a
`Resolution` with no resolved entity and an empty `candidates` list —
never raise.

#### Scenario: A query matching nothing returns an empty resolution, not an error
- **WHEN** `resolve` is called with a query matching no vacancy id, no
  company slug, and no company name at any tier
- **THEN** the returned `Resolution` has no resolved entity, no
  candidates, and no exception is raised

### Requirement: resolve's tier order is exact-id, then company, then fuzzy
`resolve(query)` SHALL evaluate tiers strictly in the order exact id,
exact `company_slug`, case-insensitive company name, fuzzy company
name — stopping at the first tier that resolves unambiguously —
even when a query would also match a different entity at a
lower-priority tier.

#### Scenario: Resolution order is exact-id before company before fuzzy
- **WHEN** `resolve` is called with a query that equals one vacancy's
  `id` and also equals or closely matches a different company's name
- **THEN** the returned `Resolution` identifies the vacancy, not the
  company
