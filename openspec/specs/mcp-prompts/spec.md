# mcp-prompts

## Purpose
Defines the MCP server's prompt endpoints — `prep_interview`, `draft_reply`,
and `weekly_review` — which compose prompt messages from real vault content
retrieved via existing `core.py` calls, never fabricating content.

## Requirements

### Requirement: prep_interview returns a dossier composed from real vault content
`prep_interview(company)` SHALL, for a company that resolves
unambiguously, return a well-formed prompt message composed from that
company's dossier, its vacancies' postings, prior notes, and any
take-home documents — each read via an existing `core.py` call, never
fabricated.

#### Scenario: prep_interview on a known company references its real vacancies and documents
- **GIVEN** a vault company with one vacancy that has a posting
  document and a note
- **WHEN** `prep_interview` is invoked with that company's name
- **THEN** the returned prompt message references that vacancy's real
  posting content and note content, and does not reference any company,
  vacancy, or document absent from the vault

### Requirement: prep_interview on an unknown company returns a resolution failure, not a fabrication
`prep_interview(company)` SHALL, when `company` does not resolve to
exactly one company (no match, or an ambiguous match), return a message
describing the resolution failure — naming the ambiguous candidates
when there are any — and SHALL NOT return a fabricated dossier.

#### Scenario: prep_interview on a company absent from the vault reports no match
- **GIVEN** a vault with no company matching "Nonexistent Corp"
- **WHEN** `prep_interview` is invoked with `company="Nonexistent Corp"`
- **THEN** the returned message reports that no company resolved, and
  invents no dossier content

#### Scenario: prep_interview on an ambiguous company name reports the candidates
- **GIVEN** a vault with two companies whose names both fuzzy-match
  "Acme"
- **WHEN** `prep_interview` is invoked with `company="Acme"`
- **THEN** the returned message names both candidate companies and
  does not pick one to fabricate a dossier for

### Requirement: draft_reply returns the vacancy's thread and prior tone from real content
`draft_reply(vacancy_id)` SHALL, for a `vacancy_id` that resolves,
return a well-formed prompt message composed from that vacancy's
filed email/note documents, referencing their real content.

#### Scenario: draft_reply references a vacancy's real prior correspondence
- **GIVEN** a vacancy with two filed email documents
- **WHEN** `draft_reply` is invoked with that vacancy's id
- **THEN** the returned prompt message references both filed emails'
  real content

### Requirement: weekly_review surfaces stale applications, pending take-homes, and needs-review vacancies
`weekly_review()` SHALL return a prompt message composed from
`core.list_vacancies` calls filtering on staleness, `take_home` status,
and the `needs_review` tag — each section reflecting real vault
content.

#### Scenario: weekly_review lists a stale vacancy, a pending take-home, and a needs-review vacancy
- **GIVEN** a vault with one vacancy stale beyond a threshold, one at
  `take_home` status, and one tagged `needs_review`
- **WHEN** `weekly_review` is invoked
- **THEN** the returned prompt message's content includes all three
  vacancies, each attributed to the section its filter matched
