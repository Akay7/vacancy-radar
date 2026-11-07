## Why

The vault records *that* a vacancy was applied to, but not *with what*.
Someone sending several resume variants — one per target position, or
two phrasings of the same one run side by side as an A/B test — has no
way to say which variant went to which employer, and so no way to see
which one actually gets answered. Today the only trace is a free-text
`stage_note` or a `tags` entry, neither of which can be aggregated.

## What Changes

- Add an optional `resume` field to a vacancy: a short free-form label
  (`backend-v2`, `data-eng-short`) naming the resume variant that was
  sent. The label is the only identity a variant has — the vault does
  not store or version resume files.
- Accept `resume` everywhere a vacancy is written: `create_vacancy`,
  `set_status` (the `found` → `applied` move is when it is usually
  known), and `edit_vacancy` (settable and clearable, with the usual
  edit-history entry). The CLI gets matching `--resume` options.
- Surface `resume` on `VacancySummary` and `VacancyDetail`, and add a
  `resume` filter to `list_vacancies`, so "every application sent with
  `backend-v2`" is one call.
- Add a **resume comparison**: `core.resume_stats`, the CLI command
  `vacancy-radar resumes`, and the MCP read tool `resume_stats`. For
  each label it reports how many applications used it and how they
  currently stand (still applied / advanced / rejected / ghosted), plus
  an advance rate. Applications recorded without a resume are grouped
  under an explicit "no resume recorded" row so the totals add up.
- Keep the tool surface otherwise unchanged: `resume_stats` is the one
  new MCP tool (twelve → thirteen), read-only, with no `ui://` view.

Non-goals: storing resume files or diffs; assigning variants to
vacancies automatically; statistical significance testing (the report
gives counts and rates and leaves the judgement to the reader); a
`resume` column or filter in the search index; showing `resume` in the
MCP Apps views.

## Capabilities

### New Capabilities
- `resume-tracking`: the `resume` vacancy field and its validation, its
  exposure on summaries/detail and the `list_vacancies` filter, and the
  per-resume comparison (`resume_stats`) across core, CLI and MCP.

### Modified Capabilities
- `vacancy-editing`: `resume` becomes the tenth editable (and
  clearable) field.
- `mcp-write-tools`: the `edit_vacancy` tool schema gains `resume`;
  `set_status` and `create_vacancy` gain a matching optional argument.
- `cli-write-commands`: `edit`, `status set` and `new` gain `--resume`.
- `status-transitions`: `set_status` may also write `resume` (and an
  edit-history entry) without breaking its "every other line is
  preserved" guarantee.
- `mcp-transport`: the tool list grows by `resume_stats`.

## Impact

- Code: `models.py` (`Vacancy.resume`), `core.py` (`edit_vacancy`,
  `set_status`, `create_vacancy`, `list_vacancies`, `get_vacancy`,
  new `resume_stats`), `cli.py`, `mcp_server.py`.
- Vault format: one new optional frontmatter key. Existing vaults stay
  valid with no migration; older versions of the tool ignore or
  preserve the unknown key per the existing frontmatter round-trip.
- Index: unchanged. `resume` is read from the vault snapshot, not the
  LanceDB table, so no schema change and no forced reindex.
- Sequencing: the `mcp-transport` delta is written against the tool
  list as `add-mcp-apps-ui` leaves it (twelve tools), so that change
  must be archived before this one is applied.
- Docs: README MCP/CLI reference, CHANGELOG `[Unreleased]` (tag
  `v0.2.0` exists).
