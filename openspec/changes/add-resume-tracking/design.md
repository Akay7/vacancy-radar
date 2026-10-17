## Context

A vacancy's frontmatter (`models.Vacancy`) is the single record of an
application; `set_status` and `edit_vacancy` rewrite it atomically and
leave a history entry, and `list_vacancies`/`get_vacancy` read it from
the vault snapshot, not the index. `Vacancy` ignores unknown
frontmatter keys and the write paths re-parse and re-serialize the raw
metadata, so a new key survives older writers. See `proposal.md` for
motivation.

The in-flight `add-mcp-apps-ui` change (28/29 tasks) edits the
`mcp-transport` tool-list requirement and the `ui://` views; this
change builds on its end state.

## Goals / Non-Goals

**Goals:**
- Record which resume variant an application used, with no manual
  bookkeeping beyond naming it once.
- Make the variants comparable with one call, with every number
  traceable to vacancies the user can list.
- Stay inside the existing invariants: vault is truth, writes validated
  and recorded, MCP tool is a thin delegate, index untouched.

**Non-Goals:**
- Resume file storage, diffing, or templates.
- Significance testing or any "winner" verdict.
- Per-resume search filtering (would need an index schema change).
- Resume display in the `ui://` views (they are mid-change; a follow-up
  can add one field to the detail card).

## Decisions

### 1. A free-form label on the vacancy, not a registry of resumes
`resume` is an optional string in `vacancy.md` frontmatter. Distinct
labels are discovered from the vault.

*Alternatives:* a `resumes.yaml` registry (validates labels, but adds a
second source of truth to keep in sync and a step before first use); a
resume as a `DocumentKind` filed under the vacancy (ties a variant to
one vacancy's folder — the same resume would be filed N times and
could not be grouped without hashing content); reusing `tags`
(already works today, but is unvalidated, unordered, and mixed with
`needs-review` and user tags, so aggregation would have to guess which
tag is the resume).

Free-form means typos split a variant. Mitigation: case-insensitive
grouping, and `resume_stats` listing every label so a stray one is
visible, fixable with `edit_vacancy`.

### 2. Normalization: trim on write, casefold on compare
The stored value is trimmed and kept as typed; filtering and grouping
compare case-insensitively, and `resume_stats` reports the lower-cased
label. Max 64 characters and a single line, so a label cannot smuggle a
paragraph into a table or an edit-history line. Validation lives in a
`Vacancy` field validator beside `role`'s, so every write path
(create, set_status, edit) gets it for free via the existing
whole-model validation.

*Alternative:* lower-case on write — rejected: it rewrites what the
user typed and makes `edit` history show a change they did not make.

### 3. Allowed at any status; counted only once applied
The model does not tie `resume` to `applied_date` the way it ties
`applied_date` to status. A user often decides the resume before
sending, and forcing the order would make `found` + `edit --resume`
an error. The analysis side is where "applied" matters: `resume_stats`
counts only vacancies off `found`, so a staged label never inflates a
variant.

### 4. Where it can be set
- `create_vacancy(..., resume=)` — appended after `tags` in the
  existing positional list (the docstring already tells callers to use
  keywords); the MCP/CLI surfaces always pass keywords.
- `set_status(..., resume=)` — the natural moment, since moving off
  `found` is "I just applied". Written in the same atomic write as the
  status. A changed value appends an `## Edit History` line in the
  existing `field: old -> new` format via the same helper
  `edit_vacancy` uses, so invariant 3 (writes record what they
  changed) holds without a second history format. A same-status call
  remains a no-op and ignores `resume`; the user changes it with
  `edit_vacancy`.
- `edit_vacancy(resume=)` — tenth editable field, nullable, so it
  joins `EDITABLE_FIELDS` / `NULLABLE_EDITABLE_FIELDS` and the CLI/MCP
  surfaces pick it up through `resolve_field_edits` unchanged.

### 5. `resume_stats` reads outcomes from current status
Buckets come from the vacancy's current `status`, with `advanced` =
`screening | take_home | interview | offer`. Rows carry a full
per-status count (so nothing is hidden by the summary) plus `advanced`
and `advance_rate`.

*Alternative considered:* derive "got a response" from the `## Status
History` block, so a vacancy later rejected after screening still
counts as a response. More faithful, but it makes the answer depend on
parsing free-text history that older vaults and imports may lack. Not
needed to be useful; the per-status counts let a reader see the
rejected share. Can be added later without changing the row shape
(`advanced` would just be computed differently).

Result type: a `ResumeStats` row model (`resume`, `applications`,
`by_status`, `advanced`, `advance_rate`) in `core.py`, returned as
`list[ResumeStats]`; computed from one `read_vault` snapshot, like
`list_vacancies`. No index access, so it works with a missing or stale
index.

### 6. Surfaces
- CLI: `vacancy-radar resumes [--since DATE] [--json]`, a rich table
  matching `list`'s style; `--resume` on `edit`, `status set`, `new`;
  `--resume` filter on `list`.
- MCP: `resume_stats` tool, `_READ_ONLY` annotations, `_delegate` wrapper,
  one `core.resume_stats` call, no `_meta.ui`. `list_vacancies` gains
  an optional `resume` argument; `set_status`, `create_vacancy`,
  `edit_vacancy` gain `resume`. The server's tool docstrings mention
  the A/B use so an LLM client knows to ask for the label when the
  user says "I sent my new CV".

### 7. No index schema change
`resume` is not added to `DocumentRow`. A new column would force every
existing index to rebuild and is only useful for search filtering,
which is a non-goal. The `list_vacancies` filter works on the vault
snapshot as `status`/`company` already do.

## Risks / Trade-offs

- [Label typos split a variant] → case-insensitive grouping;
  `resume_stats` lists all labels; `edit` fixes them. No fuzzy merging.
- [Advance rate understates responses for vacancies already rejected
  after an interview] → full per-status counts in each row; documented
  in the CLI help and README; history-based refinement left open.
- [Small samples read as signal] → rows always show absolute
  `applications`; no percentage-only output and no "best resume"
  claim. A typical user will have single-digit counts per variant.
- [Confounding: variants sent to different positions are not a fair
  comparison] → the tool does not control for it; README says to
  compare variants sent to comparable roles. Users can filter listing
  by `resume` and read the vacancies.
- [Ordering dependency on `add-mcp-apps-ui`] → its delta is the base
  for this `mcp-transport` change; archive it first.

## Migration Plan

None required: the key is optional and absent from existing vacancies.
Existing applications show under the "no resume recorded" row until
backfilled with `edit --resume`. Rollback is removing the code; the
extra frontmatter key is ignored by earlier versions and preserved on
their writes.

## Open Questions

- Whether the detail/list `ui://` views should show the resume — a
  small follow-up once `add-mcp-apps-ui` is archived; not needed for
  tracking to work.
