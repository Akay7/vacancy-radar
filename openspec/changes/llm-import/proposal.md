## Why

Stages 1-8 gave vacancy-radar a vault, retrieval, a CLI, and an MCP
server — but no way to get an existing tracker into the vault at all
short of typing every row by hand through `vacancy-radar new`. Stage 9
closes that gap without an importer: the user pastes rows or points
Claude at a source, and Claude calls MCP tools directly, turn by turn,
with the user reviewing each batch. That requires exposing
`create_vacancy` over MCP — stage 8 deliberately excluded it — and a
way for the calling model to check for a duplicate before creating,
since `create_vacancy` still doesn't deduplicate.

## What Changes

- **Reverse stage 8's exclusion of `create_vacancy`.** Stage 8's
  design.md (Decision 1) kept it CLI-only because a misclassification
  by a batch importer would be invisible. Conversational import has no
  batch script — every call is a turn in a conversation the user reads
  — so the exclusion's premise no longer holds. `reindex` stays
  excluded; nothing about this change gives a model a legitimate
  reason to trigger a full reindex.
- Expose `create_vacancy` as an MCP write tool
  (`readOnlyHint: false`, `destructiveHint: false`,
  `openWorldHint: false`), delegating to `core.create_vacancy`
  unchanged in spirit — extended in signature (see below) — with no
  filtering, sorting, or dedupe logic added in the server.
- Extend `core.create_vacancy`'s signature with four optional
  parameters that already exist on the `Vacancy` model but were never
  settable at creation time: `stage_note`, `salary_note`, `recruiter`,
  `tags`. Without this, the MCP tool would need to reconstruct these
  fields itself after the fact — logic the server isn't allowed to
  have.
- Add `core.find_existing(company, source_url)`, a new read-only core
  function combining `resolve`'s company-matching tier with a
  `source_url` scan across the vault, and expose it as an MCP read
  tool (`readOnlyHint: true`) so a model can check before creating
  instead of discovering a duplicate from a collision-suffixed id
  after the fact.
- Update the tool list's fixed-exclusions requirement: eleven tools
  now, not nine — `reindex` is still the only write-shaped capability
  withheld from the model.
- Add `docs/import-guide.md`: how to import an existing tracker by
  conversation — triage, batch size, stage-vocabulary mapping,
  role-from-URL derivation, per-batch verification, and the
  non-transactional failure mode.
- Amend `docs/evaluation.md` (new file, splitting the real-corpus
  procedure out of README.md's retrieval-evaluation section) with the
  second eval run's procedure, against a real vault after import — no
  numbers shipped from someone else's vault.

## Capabilities

### New Capabilities

- `vacancy-lookup`: `core.find_existing(company, source_url)` —
  matches an existing vacancy by resolved company or by exact
  `source_url`, returning `VacancySummary` rows, never raising on an
  unresolved company.

### Modified Capabilities

- `mcp-write-tools`: `create_vacancy` joins `append_note`,
  `set_status`, and `add_document` as a fourth exposed write tool —
  delegation, schema, annotation, and typed-error requirements mirror
  the existing three; new requirements cover the schema's `status`
  enum (from `models.py`), the tool description's stated import
  conventions (`unknown`/`needs_review`, synthesized `found_date`/
  `migrated`, check-before-create), and repeated-call (batch) behavior.
- `mcp-read-tools`: `find_existing` joins the six exposed read tools,
  delegating to the new `core.find_existing`.
- `mcp-transport`: the tool-list requirement changes from "exactly the
  nine specified tools, excluding `reindex`, `create_vacancy`" to
  "exactly the eleven specified tools, excluding `reindex`" —
  `create_vacancy` is no longer in the exclusion list; `find_existing`
  joins the list.
- `vacancy-creation`: `create_vacancy`'s signature gains four optional
  parameters (`stage_note`, `salary_note`, `recruiter`, `tags`),
  forwarded to the `Vacancy` model unchanged — no new validation rule,
  since the model already validates these fields when present.

## Impact

- Modified files: `src/vacancy_radar/core.py` (`create_vacancy`
  signature; new `find_existing` function),
  `src/vacancy_radar/mcp_server.py` (two new tools, one write-tool-list
  update), `README.md` (tool table, tool count, eval-limitations
  paragraph now pointing at `docs/evaluation.md`).
- New files: `docs/import-guide.md`, `docs/evaluation.md`.
- New tests in `tests/test_core.py` (signature extension,
  `find_existing`) and `tests/test_mcp_server.py` (both new tools,
  updated tool-count/exclusion assertions).
- No new runtime dependency. No importer module, interchange format,
  or spreadsheet parser — mapping a tracker's columns onto this
  vault's vocabulary is done in conversation, per row or per batch,
  not by a schema.
- No change to `cli.py`: `vacancy-radar new` keeps its existing four
  positional-ish options; the new `create_vacancy` parameters are
  reachable from the CLI only by a later, separate change if that
  turns out to matter.
