## Context

`core.py` exposes four write paths today: `append_note` and `add_document`
(create a new file, never touch an existing one), `create_vacancy` (writes
with `overwrite=False`), and `set_status` (the single path that rewrites an
existing `vacancy.md`). `set_status` already establishes every mechanic this
change needs: parse the file with `frontmatter.parse`, mutate specific keys
in the parsed `CommentedMap`, re-validate by constructing a `Vacancy` from
the merged metadata, append a dated line to a history block in the body,
`_atomic_write(..., overwrite=True)`, then `reindex`. What it does not do is
touch anything but `status`/`applied_date`.

The constraint that shapes this change is architectural invariant 3 — writes
are append-only or validated status transitions. A field edit is neither. The
resolution chosen (see decision 5) is that the *frontmatter* may be
overwritten, but the vault still gains an append-only record of what changed,
so the markdown remains a complete history rather than a snapshot whose past
lives only in git.

## Goals / Non-Goals

**Goals:**

- One core entry point that can set several vacancy fields in a single
  validated, atomic write, with a typed error for every rejection.
- No path by which an edit can leave `vacancy.md` failing `Vacancy`'s own
  validators, or leave the index disagreeing with the vault.
- An in-vault record of every applied edit, in the same shape as the
  status-history entries a reader already knows.
- CLI and MCP surfaces that are thin marshalling over the core function,
  per invariant 4.

**Non-Goals:**

- Changing a vacancy's company (would relocate its directory), its `id`, or
  its `status` (owned by `set_status` and its transition graph).
- Editing `_company.md` — company name, domains, recruiters, notes.
- Bulk edits across vacancies, or undo/revert of a recorded edit.
- Rewriting anything in the body other than the history blocks — including
  the `# {role}` H1 that `create_vacancy` writes (decision 8).

## Decisions

### 1. One `edit_vacancy` with explicit keyword parameters, not a field dict

`edit_vacancy(vacancy_id, *, source_url=..., role=..., ...)` names each
editable field in its signature, the way `create_vacancy` does.

*Why:* the signature becomes the definition of what is editable — passing
`status=` or `company=` is a `TypeError` at the call site, with no runtime
allow-list to keep in sync. It also gives the MCP tool a typed schema for
free (the server generates it from the annotations) and the CLI a natural
option per field.

*Alternative considered:* `edit_vacancy(vacancy_id, fields: dict[str, Any])`.
Rejected — it pushes name validation to runtime, produces an opaque MCP
schema, and invites callers to pass `id` or `status` and get a late error.

### 2. An `UNSET` sentinel separates "not given" from "clear this field"

Most editable fields are `str | None`, so `None` is a legitimate *value* —
it means "clear it". A module-level sentinel, `UNSET`, is the default for
every field parameter; only parameters that are not `UNSET` participate in
the edit.

*Why:* without it, `edit_vacancy(v, recruiter=None)` is ambiguous — it can't
mean both "leave the recruiter alone" (the natural reading of an omitted
default) and "remove the recruiter".

*Alternative considered:* a separate `clear: list[str]` parameter on the core
function, with `None` meaning "leave alone". Rejected for the core API — it
makes the type of a clear different from the type of a set, and two ways to
express the same intent. It *is* the right shape one layer up (decision 9),
where JSON and CLI flags can't carry a Python sentinel.

### 3. Editable set: nine fields; `id`, `status`, `company`, `company_slug` are not

Editable: `source_url`, `role`, `stage_note`, `salary_note`, `recruiter`,
`external_id`, `tags`, `found_date`, `applied_date`.

- `id` is immutable per `vacancy-identity`, and the vacancy's directory is
  named after it.
- `status` has its own function and a transition graph; letting `edit` set
  it would create a second, unvalidated path around `STATUS_TRANSITIONS`.
- `company`/`company_slug` determine where the vacancy directory lives.
  Editing them without moving the directory would desync the vault layout;
  moving it is a distinct piece of work (a non-goal here).

Note that `found_date` is editable even though `ids.new_vacancy_id` derives
part of the id from it: the id is minted once and never re-derived, so
correcting a mistyped `found_date` fixes the data without renaming anything.
The id keeps the original date fragment; the edit-history entry is what
explains the discrepancy to a later reader. Same for `role`.

### 4. Validate by constructing a whole `Vacancy`, reusing `InvalidVacancyDataError`

The merged metadata mapping is passed to `Vacancy(**metadata)` before any
byte is written; a `ValidationError` is wrapped in the existing
`InvalidVacancyDataError` and the file is left untouched.

*Why:* the interesting failures here are cross-field, not per-field —
clearing `applied_date` while `status` is not `found`, setting `found_date`
later than an existing `applied_date`, emptying `role`, a non-http
`source_url`. Only a full model construction catches all of them, and
`models.py` already owns those rules. Re-implementing per-field checks in
`core.py` would be a second, drifting copy of the model.

*Consequence:* an edit can be rejected by a rule about a field the caller
did not touch (e.g. setting `found_date` after today). That is correct — the
file must be valid as a whole — and the wrapped `ValidationError` message
names the offending field.

### 5. A `## Edit History` block, appended per edited field

Every applied edit appends one line per changed field under a
`## Edit History` heading in the body:

```
## Edit History
- 2026-08-11: source_url: https://old.example/jobs/1 -> https://new.example/careers/1
- 2026-08-11: recruiter: (none) -> Anna K.
```

Old and new values are rendered from the frontmatter's serialized form;
absent values render as `(none)`. Multi-line values (`stage_note`) are
recorded as a single-line summary rather than embedded verbatim, so a note
containing a newline cannot forge a second history entry.

*Why a separate block rather than reusing `## Status History`:* the two
answer different questions ("how did this application progress?" vs "what
did I correct about this record?") and a reader scanning a pipeline history
should not have to filter out URL corrections. It also keeps `set_status`
and `edit_vacancy` from contending over one block's format.

*Why in-vault at all:* invariant 1 — the vault is the source of truth and the
index is disposable. A change recorded only in git is invisible to every
reader of the vault, including the MCP tools an LLM uses.

### 6. Both history blocks are appended section-aware, not at end-of-file

`_append_status_history` today appends the entry at the very end of the body,
relying on `## Status History` being the last section. Once `## Edit History`
can sit below it, that assumption breaks — status entries would land inside
the edit block.

The fix is a shared helper, `_append_to_section(body, heading, entry)`, that
locates the heading and inserts after the last line of *that* section (up to
the next `##` heading or end of body), creating the section at the end of the
body when it is absent. `_append_status_history` and the new
`_append_edit_history` both call it. When `## Status History` is in fact the
last section, the output is byte-identical to today's, so
`status-transitions`' existing requirements are unaffected.

Canonical ordering when both exist: `## Status History` first, then
`## Edit History` (whichever is created first stays where it is; a newly
created block goes at the end of the body).

### 7. No-op edits write nothing

An edit is a no-op when no field parameter was given, or when every given
value already equals the vacancy's stored value (compared on the parsed
`Vacancy`, not on raw YAML text, so `tags: []` and an absent `tags` compare
equal). A no-op returns an `EditResult` with `changed=False` and an empty
`changed_fields`, writes no file, appends no history line, and does not
reindex.

*Why:* it mirrors `set_status`'s same-status no-op exactly, and it keeps an
idempotent re-run (an LLM retrying a tool call) from filling the history
block with `X -> X` lines.

### 8. The body is otherwise never rewritten

Changing `role` does not rewrite the `# {role}` H1 that `create_vacancy`
seeds, and no edit touches any other body line. The strong guarantee — every
byte outside the touched frontmatter keys and the appended history line is
preserved — is worth more than a heading that agrees with frontmatter, and
the vault is hand-edited, so the H1 may have been deliberately changed.

### 9. CLI and MCP express "clear" as a named field list

Neither surface can carry the `UNSET` sentinel: Typer options default to
`None`, and a JSON-RPC client's omitted-vs-`null` distinction is not reliable
across MCP clients. Both therefore take a repeatable/list `--clear FIELD` /
`clear: list[str]` argument alongside the per-field value options, and
translate to the core call: a value option that was given maps to that value,
a field named in `clear` maps to `None`, anything else stays `UNSET`. Naming
the same field in both is a typed error (`ConflictingEditError`); naming a
field that is not editable, or is editable but not nullable (`role`,
`found_date`, `tags`), is a typed error (`UneditableFieldError` /
`NotNullableFieldError`) — these are the only runtime name checks in the
design, and they exist because these two surfaces pass field names as strings.

`--tags` replaces the whole list rather than appending; `--clear tags` is
rejected in favour of `--tags ""`, which sets the empty list — appending a
tag is a read-then-write the caller performs.

### 10. `project.md` invariant 3 is restated

"Writes are append-only or validated status transitions" becomes "Writes are
append-only, validated status transitions, or validated field edits that
record what they changed." The spirit — no silent, unvalidated mutation —
is unchanged; the letter has to admit the new path rather than have the
codebase quietly contradict it.

## Risks / Trade-offs

- **A vacancy's `id` can disagree with its `found_date`/`role` after an
  edit** → Accepted deliberately (decision 3); ids are opaque handles, not
  derived keys, and the edit-history entry explains the discrepancy.
- **Rejection on a field the caller did not touch** (decision 4) → The
  wrapped `ValidationError` names the field, and the CLI prints it; the
  alternative (partial writes) is worse.
- **Two history blocks make a hand-edited body easier to get wrong** →
  `_append_to_section` creates a missing block rather than failing, and both
  blocks share one line format, so a human writing an entry by hand in either
  block produces something the next append preserves.
- **Every edit triggers a `reindex`** → Same cost `set_status` already pays
  on every status change; a field edit is a rare, interactive operation.
- **`stage_note` edits lose their multi-line content in the history line**
  (decision 5) → The full new value is in frontmatter and the full old value
  is in git; the history line is a pointer, not a backup.
- **Concurrent edits are last-write-wins** → Unchanged from `set_status`;
  the vault is single-user and `_atomic_write` still guarantees the file is
  never left half-written.
