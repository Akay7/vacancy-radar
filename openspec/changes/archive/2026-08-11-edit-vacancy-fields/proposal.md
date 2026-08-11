## Why

Today the only way to correct a vacancy's stored metadata is to hand-edit
`vacancy.md` and re-run `reindex`. Every write path the CLI and MCP server
expose is either append-only (`note`, `add`) or a status transition
(`status set`); nothing lets a user fix a field that was captured wrong or
that changed at the source — a moved posting URL, a role title that was
`unknown` at capture time and is now known, a corrected recruiter name, a
`found_date` typo. Hand-editing bypasses `Vacancy`'s validators entirely
and silently leaves the index stale, so the one operation a tracker needs
most often is also the one that most easily corrupts the vault.

## What Changes

- New `core.edit_vacancy(vacancy_id, **fields)` that sets one or more
  mutable frontmatter fields in a single validated, atomic write, then
  refreshes the index — the same contract `set_status` already honours.
- Editable fields: `source_url`, `role`, `stage_note`, `salary_note`,
  `recruiter`, `external_id`, `tags`, `found_date`, `applied_date`.
  Each accepts a new value or an explicit clear (for the nullable ones).
- Not editable: `id` (immutable by `vacancy-identity`), `status` (already
  owned by `set_status`, with its transition graph), and
  `company`/`company_slug` (changing them means relocating the vacancy
  directory — out of scope, called out as a non-goal below).
- Every applied edit appends a `## Edit History` entry to `vacancy.md`'s
  body — `- <date>: <field>: <old> -> <new>` — mirroring the existing
  `## Status History` block, so an overwrite of frontmatter still leaves
  an append-only record in the vault.
- New `vacancy-radar edit <vacancy>` CLI command with one option per
  editable field, `--json` output, and the same resolve-or-fail behaviour
  the other write commands share.
- New `edit_vacancy` MCP write tool delegating to the core function with
  no logic of its own.
- A no-op edit (every given value already equal to what is stored, or no
  field given at all) writes nothing, appends no history, and reports
  itself as unchanged.

Non-goals: moving a vacancy between companies; editing `_company.md`
(company name, domains, recruiters, notes); bulk edits across vacancies;
undo/revert of a recorded edit.

## Capabilities

### New Capabilities
- `vacancy-editing`: the `core.edit_vacancy` contract — which fields are
  editable, how values are set and cleared, validation before write,
  atomicity, no-op semantics, and index refresh.
- `edit-history`: the `## Edit History` block — when an entry is
  appended, its format, its placement relative to `## Status History`,
  and the guarantee that unrelated body lines are preserved byte-for-byte.

### Modified Capabilities
- `cli-write-commands`: adds `edit` to the set of write commands bound by
  the existing exit-code, ambiguous-match, and `--json` requirements.
- `mcp-write-tools`: adds `edit_vacancy` to the exposed write tools,
  under the existing delegation and error-marshalling requirements.

## Impact

- `src/vacancy_radar/core.py` — new `edit_vacancy`, a typed
  `NoEditableFieldsError`/`ImmutableFieldError`, an `EditResult` dataclass,
  and an `_append_edit_history` helper alongside `_append_status_history`.
- `src/vacancy_radar/cli.py` — new `edit` command and its option parsing.
- `src/vacancy_radar/mcp_server.py` — new `edit_vacancy` write tool.
- `openspec/project.md` — architectural invariant 3 ("writes are
  append-only or validated status transitions") needs restating to cover
  validated field edits that leave an append-only history entry.
- Tests under `tests/` for core, CLI, and MCP surfaces.
- No new dependencies. No change to `models.py`, the index schema, or the
  vault layout.
