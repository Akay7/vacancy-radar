## Context

`core.resolve` is deliberately one function with one answer shape: a
`Resolution` naming either a vacancy or a company, or listing ambiguous
company candidates, never guessing (`entity-resolution`, cli-read's design.md
decision 3). Read commands depend on that: `show acme-corp` renders a company
dossier precisely because the company tier resolved to a company.

The write commands need something narrower — a single vacancy id — and today
each one gets it from `cli.py`'s `_resolve_vacancy_or_fail`, which branches
on the `Resolution`'s fields and rejects anything that is not already a
vacancy id. Everything below follows from those two facts: `resolve` cannot
change, and the narrowing has to live somewhere else.

## Goals / Non-Goals

**Goals:**

- Make `cli-write-commands`' stated resolution behavior true for every write
  command, in one place rather than four.
- Keep the refusal that matters: a company holding several vacancies is
  ambiguous, and no write proceeds on a guess.
- Leave `resolve` and every read command byte-for-byte unchanged.

**Non-Goals:**

- Changing `resolve`'s tiers, its return shape, or its never-raise contract.
- Query arguments on the MCP write tools.
- Any notion of "eligible" beyond "belongs to that company" — a status- or
  kind-aware filter would make the same argument mean different vacancies in
  different commands.

## Decisions

### 1. A new `core.resolve_vacancy`, not a flag on `resolve`

`resolve_vacancy(query, vault=None) -> str` calls the same internal
`_resolve` against one vault snapshot, then narrows.

*Why not a `prefer_vacancy=True` parameter on `resolve`:* `resolve` returns a
`Resolution` and never raises; the write path wants an id and typed failures.
Bolting a mode onto `resolve` would give one function two return contracts
and force every existing caller to care which one it asked for.

*Why in `core.py` and not `cli.py`:* it is a vault-reading rule about what a
query means, which is the definition of business logic. Keeping it in the CLI
is what let the four write commands silently share a shortfall instead of a
behavior.

### 2. Narrowing rule: exactly one vacancy under the company, or fail

A company-tier resolution is narrowed to that company's vacancies. One
vacancy resolves. Zero raises `EntityNotFoundError` (the query named
something real, but there is nothing to write to). More than one raises the
new `AmbiguousVacancyError`, naming the company and every candidate id.

*Why not "the most recent" or "the only active one":* every such rule is a
guess that is right most of the time, and the one time it is wrong it has
already written to the wrong vacancy. `resolve`'s existing refusal to guess
between companies is the precedent.

### 3. `AmbiguousVacancyError` is its own type

`AmbiguousEntityError` carries `ResolutionCandidate(slug, name)` — company
candidates, and its message reads "matches more than one company". A vacancy
ambiguity is a different failure with different data, so it gets its own
type carrying the company slug and the candidate vacancy ids, rather than
overloading the existing one with values whose field names would lie.

### 4. The CLI keeps only its rendering

`_resolve_vacancy_or_fail` becomes a `try/except` around `resolve_vacancy`
that routes typed errors through `_fail` — the same shape every other write
command's core call already has. Candidate rendering stays in the CLI
(`_render_candidates` for company ambiguity, the error message's own ids for
vacancy ambiguity), because presentation is the CLI's job.

### 5. Read commands are untouched

`show`, `get_company`, `get_vacancy`, `find_existing`, and the MCP tools keep
calling `resolve` and keep getting a company for a company query. No caller
of `resolve` changes; `resolve_vacancy` is purely additive.

## Risks / Trade-offs

- **A previously-failing command now writes** → That is the requirement being
  satisfied, and the narrowing is the strictest one that can satisfy it: a
  company with two vacancies still refuses. Users who relied on the failure
  as a safety net keep it everywhere it was doing real work.
- **Two resolution entry points could drift** → `resolve_vacancy` calls the
  same `_resolve`; the tier order exists in exactly one place, and a
  `resolve_vacancy` test asserts the id tier still short-circuits.
- **A one-vacancy company grows a second vacancy and the same command starts
  failing** → Correct, and the error names both ids, so the fix is to paste
  one of them. Silently continuing to write to the older vacancy would be
  the worse outcome.
