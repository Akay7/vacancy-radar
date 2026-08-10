## Context

`Vacancy.source_url: str` has been required since stage 1
(`vault-model`) and has stayed required through every later stage that
touches vacancy creation — stage 7's `create_vacancy`, stage 9's
(`llm-import`) extension of it. The gap this change closes wasn't
visible until conversational import (stage 9) made "the user just
pastes what a recruiter sent" a real, common path: a recruiter email
with a PDF attachment and no posting link at all has no `source_url`
to give, and today's required field forces either a fabricated one or
skipping the vacancy entirely.

## Goals / Non-Goals

**Goals:**
- A vacancy can be created with no `source_url`, at every layer (core,
  CLI, MCP), without weakening validation for a `source_url` that *is*
  provided.
- `find_existing` stays a reliable duplicate-check even when
  `source_url` is absent — it must not report false positives between
  two unrelated URL-less vacancies.
- Every existing caller and test that already provides a `source_url`
  keeps working unchanged in substance (call shape changes from
  positional to keyword; behavior does not).

**Non-Goals:**
- Making any other `Vacancy` field optional. This change is scoped to
  `source_url` only.
- Changing `source_url`'s validation rule when a value is given (still
  must be http/https).
- Changing vacancy-id derivation. `ids.new_vacancy_id` already derives
  from `found_date`/`company_slug`/`role` only — confirmed by reading
  it, not assumed — so nothing about id minting changes here.
- Rendering `source_url` in `vacancy-radar show`. It isn't rendered
  today (`_render_vacancy_detail` has no line for it) — a separate,
  pre-existing gap this change doesn't fix, since it's orthogonal to
  whether the field is required.
- Archiving `mcp-server`/`llm-import` first. Offered to the user,
  declined — see the note in "Working against the unarchived stack"
  below for how this change's deltas handle that.

## Decisions

### 1. The signature reorder: why, and everywhere it touches

`core.create_vacancy`'s current signature is:

```python
def create_vacancy(
    company: str, role: str, source_url: str, found_date: date,
    status: Status | str, applied_date: date | None = None,
    stage_note: str | None = None, salary_note: str | None = None,
    recruiter: str | None = None, tags: list[str] | None = None,
    *, vault: Path | None = None,
) -> Path:
```

Python requires every parameter after the first one with a default to
also have a default (for non-keyword-only parameters). `found_date`
and `status`, positions 4 and 5, stay required — there's no case where
a vacancy can exist without a found date or a status. So `source_url`
cannot keep its position-3 slot and gain a default at the same time;
it has to move to sit among the already-optional parameters
(`applied_date` onward). New order:

```python
def create_vacancy(
    company: str, role: str, found_date: date, status: Status | str,
    source_url: str | None = None, applied_date: date | None = None,
    stage_note: str | None = None, salary_note: str | None = None,
    recruiter: str | None = None, tags: list[str] | None = None,
    *, vault: Path | None = None,
) -> Path:
```

This is a real, breaking change to positional call shape — not just
"add a default." A positional call written against the old order
(`company, role, source_url, found_date, status, ...`) would, against
the new order, silently pass its `source_url` string into the
`found_date` parameter slot instead of raising a clean error. That's
worse than a `TypeError`: a confusing failure far from its cause.
Every call site in this codebase is therefore converted to keyword
arguments in the same pass, not just updated in argument order —
keyword calls can't be silently misassigned; a typo or stale
positional order becomes an immediate, clear `TypeError`. Sites
touched: `cli.py`'s `new_command`, `mcp_server.py`'s `create_vacancy`
tool, and every `core.create_vacancy(...)` call in `tests/test_core.py`
(counted: 20, via `grep -rn "core.create_vacancy("`). `Vacancy(...)`
constructor calls elsewhere (already keyword-based, per pydantic
convention) are unaffected — `source_url` there just becomes a field
that can be omitted or `None`.

### 2. find_existing's None-vs-None non-match rule

`core.find_existing` unions two tiers today: a company-resolution
match, and an exact `source_url` equality match. Making `source_url`
optional creates a real correctness hazard if the equality check isn't
guarded: naively, `vacancy.source_url == source_url` when both sides
are `None` evaluates `True` in Python, which would make *every*
URL-less vacancy in the vault "match" *every* `find_existing` call
where the caller also passed no `source_url` — exactly the
false-positive-duplicate failure mode `find_existing` exists to
prevent (llm-import design.md Decision 4: a duplicate check that lies
is worse than no check).

The fix is a guard at the one comparison site
(`core.find_existing`'s `if vacancy.source_url == source_url:` becomes
`if source_url is not None and vacancy.source_url == source_url:`) —
the source_url tier only ever contributes a row when the caller
actually gave a `source_url` to check against. A caller with no URL
(the recruiter-PDF case) still gets the company tier's results, which
is the best `find_existing` can do without one — it was never a
guarantee against duplicates, only a best-effort check (llm-import
design.md Decision 3), and this preserves that framing rather than
inventing a false one.

### 3. Working against the unarchived mcp-server + llm-import stack

Offered the user the option to archive `mcp-server` and `llm-import`
first (folding their deltas into `openspec/specs/` before this change
adds a third layer); declined. This change's delta specs for
`mcp-write-tools`, `mcp-read-tools`, and `vacancy-lookup` are therefore
written against the *current merged effective text* — mcp-server's
original `ADDED` content overlaid with llm-import's own `MODIFIED`/
`ADDED` delta — read directly from
`openspec/changes/llm-import/specs/{mcp-write-tools,mcp-read-tools,
vacancy-lookup}/spec.md` before writing a single line of this change's
deltas, not reconstructed from memory.

Requirement-by-requirement disposition (recorded here so a future
archive of all three changes together doesn't have to re-derive which
requirements this change actually touched):

**Untouched — normative text and every scenario stay true regardless
of `source_url`'s optionality:**
- `mcp-write-tools`: "each write tool delegates to exactly one
  core.py function" (its `create_vacancy` scenario passes a
  `source_url`; still valid input, not exercising the omitted case).
- `mcp-write-tools`: "write tool argument names match core.py
  parameter names" (the *set* of argument names is unchanged —
  `source_url` is still a name in it, just no longer required).
- `mcp-write-tools`: "every write tool exposes a valid JSON schema",
  "enum-typed write tool parameters...", "the four write tools carry
  readOnlyHint false...".
- `mcp-write-tools`'s four `create_vacancy`-specific `ADDED`
  requirements about company-directory creation, immediate
  listing/searchability, and collision ids — none reference
  `source_url`.
- `mcp-read-tools`: the equivalent argument-name/schema/annotation
  requirements, and `find_existing`'s three existing `ADDED`
  requirements (matches by company, empty for unknown company,
  cross-spelling match) — all already exercise a real `source_url`,
  which remains valid.
- `vacancy-lookup`'s five existing `ADDED` requirements — same
  reasoning; each already passes a real `source_url` in its scenario.

**Modified — the requirement's own content changes:**
- `mcp-write-tools`: "optional write tool parameters are genuinely
  optional" gains a `source_url` case in `create_vacancy`'s scenario
  (joining `applied_date`/`stage_note`/`salary_note`/`recruiter`/
  `tags` in the omitted-arguments list).
- `mcp-write-tools`: "create_vacancy's tool description states the
  import conventions..." gains the recruiter-PDF-only convention and
  its own scenario, alongside the existing unknown-role/migrated/
  check-before-create ones.

**Added — new requirements, no existing one covers this:**
- `mcp-write-tools`: `create_vacancy` tool's `source_url` is optional
  (end-to-end: omitting it succeeds).
- `mcp-read-tools`: `find_existing` tool's `source_url` is optional
  (end-to-end: omitting it still returns company-tier matches).
- `vacancy-lookup`: `find_existing`'s `source_url` parameter is
  optional; and the None-vs-None non-match rule (Decision 2 above) as
  its own directly-testable requirement.
- `vacancy-creation`: `create_vacancy` accepts an optional
  `source_url` (mirrors the shape llm-import's own delta already used
  for `stage_note`/`salary_note`/`recruiter`/`tags`).
- `vault-model`: `source_url` removed from the mandatory-field list;
  "may be omitted" scenario added; "must be http/https" scenario kept,
  reworded "when provided."

## Risks / Trade-offs

- [Converting ~20 test call sites from positional to keyword arguments
  touches a lot of lines for what is conceptually a small behavior
  change] → accepted: the alternative (reordering positional values in
  place) is the exact silent-misassignment hazard Decision 1 describes;
  the mechanical size of the diff is the safer choice, not a
  shortcut around it.
- [A third unarchived layer on `mcp-write-tools`/`mcp-read-tools`/
  `vacancy-lookup` makes a future archive's merge more work] →
  accepted per the user's explicit choice; mitigated by Decision 3's
  explicit requirement-by-requirement record, so the merge has a map
  to follow rather than needing to re-diff three change directories
  from scratch.

## Migration Plan

Additive at the type level (`str | None`, default `None`) but breaking
at the call-shape level for `core.create_vacancy` specifically — every
in-repo caller is updated in this same change, so nothing is left
broken. No data migration: existing vacancies already have a
`source_url` (it was required when they were created) and are
unaffected either way. Rollback is reverting the model field, the two
`core.py` signatures, and the four call-site files — no other module
depends on the new optionality.
