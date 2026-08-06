## Why

Stages 1-6 built a vault that can be read, indexed, and searched, but
every change to it still has to be a hand-edited file — there is no
programmatic way to log a note, move a vacancy's status, file a
document, or create a new vacancy, let alone do any of that from a
command line. Stage 8's MCP server needs exactly these write
operations exposed as tools; building them now, once, as library
functions in `core.py` gives both the CLI (this change) and the MCP
server (stage 8) a single implementation to call, per invariant 4 —
mirroring how stage 6 built the read half. This is also the stage
that puts invariant 3 (append-only or validated-transition writes) into
code: nothing shipped here deletes or silently overwrites vault
content.

## What Changes

- Add the write half of `src/vacancy_radar/core.py`: `append_note`,
  `set_status`, `add_document`, `reindex`, `create_vacancy` — each a
  typed function with its own typed errors, callable identically by a
  CLI command now and an MCP tool later.
- Add the permitted status-transition graph to `models.py` as data
  (not branching inside `set_status`), so a future MCP resource can
  expose it directly.
- Add five CLI commands over `core.py`'s write half: `vacancy-radar
  note`, `vacancy-radar status set`, `vacancy-radar add`, `vacancy-radar
  new`, `vacancy-radar reindex`. Every command that resolves a vacancy
  reuses stage 6's `core.resolve` and, on an ambiguous match, prints
  the candidates and exits non-zero without writing anything.
- `set_status` and `vacancy-radar status set` gain an `applied_date`
  parameter/`--applied-date` option beyond what the stage plan's prose
  listed: `Vacancy`'s existing conditional `applied_date` rule (stage 1)
  makes a transition off `found` impossible to validate without one,
  and this change requires it explicitly rather than guessing "today"
  — see design.md decision 7.
- Filenames for notes and filed documents are derived from date and
  title, never accepted from a caller — this is what makes
  `add_document` safe to expose to an LLM at stage 8, where the content
  being filed (a recruiter email) is attacker-controlled text.
  `add_document` also dedupes by `external_id`: re-filing the same
  email thread is a no-op, not a duplicate.
- Every write that touches a document refreshes the index for the
  affected row(s) before returning, so the write is immediately
  searchable in the same process — no separate `reindex` call needed
  for ordinary use. `set_status` updates the denormalized `status`
  column on that vacancy's document rows without re-embedding them.
- Nothing in this change deletes a file, overwrites an existing
  note/document, or offers a `--force`-to-delete escape hatch. The one
  exception to "never overwrite" is `vacancy.md`'s frontmatter via
  `set_status`, which rewrites the file but preserves its body
  byte-for-byte.
- No MCP tools, schemas, or transport — stage 8 remains out of scope.

## Capabilities

### New Capabilities

- `note-taking`: `append_note(vacancy_id, text, date=None)`, appending
  a dated note file under a vacancy's `documents/`, never overwriting
  an existing one, and refreshing that document's index row before
  returning.
- `status-transitions`: the permitted status graph (data in
  `models.py`) plus `set_status(vacancy_id, new_status, note=None,
  applied_date=None, force=False)`, validating the transition, writing
  frontmatter and a status-history block in `vacancy.md`, and resyncing
  the denormalized status column on that vacancy's document rows
  without re-embedding them.
- `document-filing`: `add_document(vacancy_id, kind, content, title,
  date, external_id=None)`, writing into the right `documents/`
  subdirectory under a derived, collision-safe filename, refusing to
  overwrite an existing path, and deduping by `external_id`.
- `reindexing`: `reindex(force=False)`, wrapping stage 3's
  `build_index` over a fresh vault snapshot as a library call the CLI
  and MCP server both use for an explicit full refresh.
- `vacancy-creation`: `create_vacancy(company, role, source_url,
  found_date, status, applied_date=None)`, creating the company
  directory and `_company.md` when absent and minting a collision-free
  id via stage 1's `ids.new_vacancy_id`.
- `cli-write-commands`: the `note`, `status set`, `add`, `new`, and
  `reindex` Typer commands — argument parsing, `core.resolve`-based
  vacancy lookup, and Rich/`--json` rendering only, over `core.py`'s
  write half.

### Modified Capabilities

(none — the write half is purely additive over stage 6's read
functions and stage 1-3's models, ids, frontmatter, and index-build
mechanisms; none of their existing requirements change)

## Impact

- Modified file: `src/vacancy_radar/core.py` — adds the write half
  described above, alongside stage 6's existing read half.
- Modified file: `src/vacancy_radar/models.py` — adds the status
  transition graph as data.
- Modified file: `src/vacancy_radar/cli.py` — adds `note`, `status`,
  `add`, `new`, `reindex` commands.
- New/extended tests: `tests/test_core.py`, `tests/test_models.py`,
  `tests/test_cli.py`, all operating on a temporary copy of the
  fixture vault — no test mutates `tests/fixtures/vault/`.
- No new runtime dependencies. No delete command, no `--force`-delete,
  no cleanup helper anywhere in this change.
- Downstream: stage 8 (MCP) will expose this write half as tools
  directly, relying on `add_document`'s derived filenames and
  `external_id` dedupe for safety against untrusted content.
