## Why

vacancy-radar's source of truth is a markdown vault, but nothing yet
defines what a valid vault entry looks like or how to read/write one
without corrupting it. Every later stage — the reader that walks the
vault, the index build, retrieval, the CLI, the MCP server, and the
eventual xlsx migration — needs a settled domain model, a byte-faithful
frontmatter codec, and a way to mint stable ids before any of them can
be built. This stage delivers exactly that, and nothing that depends on
directory traversal or content hashing, which are the next stage's
concern.

## What Changes

- Add `src/vacancy_radar/models.py`: `Status` (8-value enum, `found` as
  the pre-application state), `DocumentKind` enum, `UNKNOWN_ROLE`
  sentinel, and the `Vacancy`, `Document`, `Company` pydantic models —
  including the model-level conditional-`applied_date` rule, date
  coherence checks, role-placeholder derivation, and vacancy ordering.
- Add `src/vacancy_radar/frontmatter.py`: `parse`/`serialize` for YAML
  frontmatter + markdown body, byte-identical round-tripping (key order,
  body whitespace preserved), and `MissingFrontmatterError` /
  `MalformedFrontmatterError`.
- Add `src/vacancy_radar/ids.py`: `slugify` (ascii, transliterating
  non-Latin scripts) and `new_vacancy_id` (deterministic
  `{date}-{company_slug}-{role_slug}` ids with numeric-suffix collision
  resolution, no filesystem access).
- Add `tests/fixtures/generate.py`: a seeded, deterministic synthetic
  vault generator (12–20 companies, every `Status` value represented,
  repeat applications across years, `UNKNOWN_ROLE` entries) whose output
  is committed at `tests/fixtures/vault/` for later stages to read.
- Add two new runtime dependencies: a YAML library (order-preserving
  round trips) and a transliteration library (readable ascii slugs for
  non-Latin company names). Both justified in design.md; no others.

## Capabilities

### New Capabilities

- `vault-model`: the `Vacancy`, `Document`, `Company` domain types and
  their validation rules — mandatory/conditional/optional fields, date
  coherence, role-placeholder derivation, vacancy ordering.
- `frontmatter-io`: byte-faithful parsing and serialization of markdown
  files with YAML frontmatter, and the two error types that name what
  went wrong.
- `vacancy-identity`: ascii slug generation (with transliteration) and
  deterministic, collision-resistant vacancy id minting.
- `fixture-generation`: a seeded synthetic vault generator used as test
  fixtures for this and later stages.

### Modified Capabilities

(none — `package-skeleton` is unaffected by this change)

## Impact

- New files only: `src/vacancy_radar/models.py`,
  `src/vacancy_radar/frontmatter.py`, `src/vacancy_radar/ids.py`,
  `tests/fixtures/generate.py`, `tests/fixtures/vault/` (generated,
  committed), plus their test modules.
- New runtime dependencies: one YAML library, one transliteration
  library (both added to `pyproject.toml`; `lancedb`/`fastembed` remain
  excluded).
- No directory walking, globbing, or filesystem reads of a real vault —
  that's stage 2 (vault reader). No content hashing. No CLI surface
  changes.
- Establishes the exact shape every later stage reads and writes:
  getting field semantics (especially the conditional `applied_date`
  rule and id stability) wrong here means rework in every subsequent
  stage.
