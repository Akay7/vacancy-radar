## Context

The vault is markdown files with YAML frontmatter, hand-edited and
git-tracked. Nothing exists yet to say what a valid file looks like or
to read/write one safely. This stage defines that shape in isolation —
no directory walking, no hashing — so stage 2 (the vault reader) has a
fixed target to parse into, and the eventual xlsx migration has a fixed
target to emit.

Two properties matter more here than in most schema work, because the
vault is meant to survive years of hand-editing:

1. **Round-trip fidelity.** A parse-then-serialize cycle that reorders
   keys or reflows whitespace makes every future hand-edit show up as a
   noisy diff across the whole file, not just the line that changed.
2. **Id stability.** The vault is a directory of files a human may
   rename, move, or reorganize. If the id lived in the path, any of
   that breaks cross-references (documents, index, external_id dedupe).
   It must live only in frontmatter.

## Goals / Non-Goals

**Goals:**
- A `Vacancy`/`Document`/`Company` model that rejects invalid data at
  the boundary (parse time), not silently downstream.
- Byte-identical frontmatter round-tripping, including key order and
  body whitespace.
- Deterministic, collision-safe vacancy ids and company slugs, with
  readable ascii output for non-Latin company names.
- A committed, seeded fixture vault that later stages (reader, index,
  retrieval, eval) can all read without regenerating it.

**Non-Goals:**
- Reading a real vault directory. No `Path.glob`, no `os.walk` beyond
  what the fixture generator needs to write its own output.
- Content hashing, change detection, or anything else stage 2 owns.
- Parsing `_company.md` files from disk — `Company` exists as a type
  this stage; a reader for it is stage 2's job (see Decisions).
- CLI surface. This stage has no user-facing entry points.

## Decisions

**ruamel.yaml in round-trip mode, not PyYAML.** Byte-identical
round-tripping (task requirement: "including key order and body
whitespace") means the frontmatter writer must reproduce whatever a
human wrote, not just valid-but-different YAML. `ruamel.yaml`'s
round-trip loader (`YAML(typ="rt")`) preserves key order, comments, and
quoting style automatically as part of loading a `CommentedMap`; PyYAML
would need a hand-rolled `OrderedDict` representer and still couldn't
preserve quote style or blank lines within the frontmatter block. Cost:
a slower, pure-Python parser (no C extension) and a less familiar API
than PyYAML's `safe_load`/`safe_dump` — acceptable, since frontmatter
blocks are small (a few dozen keys, not megabytes) and this is the only
practical way to hit the fidelity requirement without writing a YAML
emitter from scratch.

**`text-unidecode` for transliteration, not `Unidecode`.** Both expose
the same Unicode→ASCII transliteration table (originally a Perl module
port); `text-unidecode` republishes it as public domain specifically so
downstream projects don't inherit the Artistic License/GPL terms of the
`Unidecode` PyPI package. Since `vacancy-radar` is MIT and public,
`text-unidecode` avoids a license mismatch for zero functional cost —
same table, same output (e.g. the placeholder `"Ромашка"` → `"Romashka"`,
`"Šaltinis"` → `"Saltinis"`). `slugify()` in `ids.py` wraps its output
with: lowercase, replace runs of non-alphanumeric characters with a
single hyphen, strip leading/trailing hyphens. Ampersands and
punctuation (`"Widget & Sons"`, `"Acme Inc."`) fall out of that same
non-alphanumeric collapse — no special-casing needed.

**The conditional-`applied_date` rule is a Pydantic model validator,
not a field validator.** It's named explicitly —
`_check_applied_date_matches_status` — as a `@model_validator(mode="after")`
on `Vacancy`, because it needs both `status` and `applied_date` in
scope simultaneously. A field validator on `applied_date` alone cannot
see `status` (and vice versa); implementing this as two field
validators would either need fragile ordering guarantees or duplicate
the rule. Keeping it as one named model validator makes it a single
place to read and to test.

**Dates are `date`, not `datetime`.** The vault is day-granular by
design — a human reviewing `found_date: 2026-03-04` doesn't care about
the hour. Source emails carry full timestamps; the conversion from
`datetime` to `date` (in whatever later stage ingests email metadata)
is a deliberate, one-way precision loss, not an oversight. `Document`
also uses `date`, for the same reason — the day a document was added
to the vault, not the second.

**`company_slug` is a stored field, not a computed property.** Even
though it's derived from `company` via `slugify()`, storing it (rather
than recomputing on every load) keeps it stable if `slugify()`'s
transliteration rules ever change — the id embeds `company_slug`, and
an id must never shift under a vacancy that hasn't otherwise changed.
`role_is_placeholder`, by contrast, *is* computed (a `@computed_field`
property) — it's a pure function of `role` with no independent state to
drift, so recomputing it is strictly safer than risking it going stale.

**Role slugs truncate to a fixed length, by plain slicing.** `ids.py`
defines `MAX_ROLE_SLUG_LENGTH = 50`. Truncation is `role_slug[:50]`,
not a word-boundary-aware truncation — a smarter truncation would still
need to be deterministic and would only add branches to get wrong.
Fifty characters keeps the full id comfortably under common filesystem
path-component limits (255 bytes) even for a long company slug.

**`new_vacancy_id` is a pure function; it does not mutate
`existing_ids`.** Given identical `(found_date, company_slug, role,
existing_ids)`, it always returns the same id, and it never writes to
the set it's handed. A caller minting ids for a batch (e.g. a future
migration script) is responsible for adding each returned id to its
working `existing_ids` set before the next call — that's what makes
the "migration-shaped batch" collision scenario exercise real,
sequential, caller-driven usage rather than a hidden stateful side
effect inside the id function.

**Migration will mark synthetic `found_date` values via `tags`, not a
new field.** `Vacancy.tags` already exists (`list[str]`, empty by
default); a future migration stage that has to synthesize a missing
`found_date` from `applied_date` should append a
`"found_date:synthetic"` tag rather than adding a schema field this
stage doesn't otherwise need. Recorded here as a convention for the
migration stage to follow — no code changes in this change implement
it.

**`Company` is a type only; a `_company.md` reader is stage 2's job.**
Discovering *which* files are `_company.md` requires walking the vault
directory, which this stage explicitly excludes. `frontmatter.parse()`
already gives stage 2 everything it needs to turn a `_company.md`'s
contents into a `Company` once it has the path — stage 2 supplies the
"which path" half.

**Staleness will compare against the most recent document date, not
`applied_date`.** Noted here, not implemented — it constrains how
stage 2's reader should shape its output (it needs to expose per-vacancy
document dates, not just the vacancy's own dates) even though staleness
computation itself is a later-stage concern.

## Risks / Trade-offs

- [`ruamel.yaml`'s round-trip mode is slower and its API is less
  familiar than PyYAML's] → Frontmatter blocks are small; parse-time
  cost is irrelevant at vault scale (hundreds, not millions, of files).
  Fidelity matters more than raw speed here.
- [Two new runtime dependencies (`ruamel.yaml`, `text-unidecode`)
  increase install surface] → Both are narrowly scoped, pure-Python,
  and directly required by an explicit, testable requirement
  (byte-identical round-trip; readable non-Latin slugs) — not
  speculative additions.
- [Storing `company_slug` instead of computing it risks it silently
  diverging from what `slugify(company)` would produce today] →
  Accepted deliberately: id/slug stability across a `slugify()` rule
  change matters more than the slug always reflecting the latest
  transliteration table. A future consistency-check tool (not this
  stage) could flag drift without forcing a rewrite.
- [Fixed 50-character role-slug truncation could produce collisions
  between two long, similar role titles] → Collision resolution
  (numeric suffix against `existing_ids`) already exists for exactly
  this case; truncation makes collisions somewhat more likely but
  doesn't introduce a new failure mode.

## Migration Plan

Greenfield — no existing vault to migrate in this stage. The xlsx
migration is a separate, later stage; this change only records the
`found_date:synthetic` tagging convention that stage will need.

## Open Questions

None outstanding — the design notes requested in scope are all resolved
above. If `ruamel.yaml`'s round-trip guarantees prove insufficient for
some hand-edited YAML style encountered later (e.g. unusual flow-style
mappings), that would surface as a failing round-trip test in this
stage, not as a silent gap.
