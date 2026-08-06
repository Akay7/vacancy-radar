## Why

Stages 1-5 built a vault that can be read (`vault/reader.py`), diffed
into an index (`index/build.py`), and searched (`index/search.py`) —
but nothing yet turns any of that into an answer a person can type a
command and look at. There is no way to list vacancies, ask "have I
dealt with this company before," or read a document, short of
importing internals in a REPL. Stage 8's MCP server needs exactly
these same read operations wrapped as tools; building them now, once,
as library functions gives both the CLI (this change) and the MCP
server (stage 8) a single implementation to call, per invariant 4.

## What Changes

- Add `src/vacancy_radar/core.py`, the project's first module holding
  business-logic entry points rather than a single mechanism. Five
  read functions: `resolve`, `list_vacancies`, `get_company`,
  `get_vacancy`, `read_document`, plus a thin `search` wrapper over
  stage 4's `index.search.search` that attaches vault resolution and
  index-staleness checking.
- Add four CLI commands over `core.py`: `vacancy-radar list`,
  `vacancy-radar show`, `vacancy-radar search`, `vacancy-radar
  doctor`. Every command supports `--json` for machine consumption
  alongside a Rich-table default for humans.
- Add a public `vacancy-radar eval` command that runs the existing
  eval harness (`eval/run.py`'s `run_eval` over `FULL_SWEEP`) and
  replaces the hidden `_eval` command from the eval-harness change.
  `_eval` is removed.
- **BREAKING**: `vacancy-radar _eval` no longer exists; its behavior
  moves to `vacancy-radar eval`, which is documented and shown in
  `--help`.
- Nothing writes to the vault or the index. `append_note`,
  `set_status`, `add_document`, and any MCP tool/schema/transport are
  explicitly out of scope — stages 7 and 8.

Note on the stage plan's "remove the private `_search` entry point
from stage 4": no such command exists in `cli.py` today (only the
eval-harness change's `_eval` does; the retrieval change never added
a hidden `_search` command). There is nothing to remove there — see
design.md.

## Capabilities

### New Capabilities

- `entity-resolution`: `resolve(query)`, the ordered exact-id /
  exact-slug / case-insensitive / fuzzy lookup strategy shared by
  `show` and every other query-by-name entry point, including the
  future MCP server.
- `vacancy-listing`: `list_vacancies(...)`, the filtered, sorted,
  bounded dashboard query over vacancy summaries.
- `company-dossier`: `get_company(name)`, a bounded cross-time view of
  one company: its vacancies, recruiters, domains, and standing notes.
- `vacancy-detail`: `get_vacancy(id_or_query)`, one vacancy's full
  frontmatter, stage note, and document index (paths and titles, no
  bodies).
- `document-reading`: `read_document(path)`, full text of one vault
  file, rejecting any path that resolves outside the vault.
- `index-freshness`: the staleness check comparing the vault's current
  document set against what the index actually has, returning a
  warning (never raising) and its degraded-not-blocked contract —
  shared by `core.search` and `vacancy-radar doctor`.
- `vacancy-search`: `core.search(...)`, the pass-through wrapper that
  resolves the vault, forwards to `index.search.search`, and attaches
  an `index-freshness` warning to the result.
- `cli-read-commands`: the `list`, `show`, `search`, `doctor`, and
  `eval` Typer commands — argument parsing and Rich/`--json` rendering
  only, over `core.py`; removal of the hidden `_eval` command.

### Modified Capabilities

(none — `search.py`'s ranking behavior is untouched; `vacancy-search`
above is a new wrapping capability, not a change to the existing
`search` spec)

## Impact

- New file: `src/vacancy_radar/core.py`.
- Modified file: `src/vacancy_radar/cli.py` — adds `list`, `show`,
  `search`, `doctor`, `eval`; removes `_eval`.
- New tests: `tests/test_core.py` (or `tests/core/test_*.py`),
  extending `tests/test_cli.py`.
- No new runtime dependencies — `resolve`'s fuzzy matching uses the
  standard library (`difflib`), not a new package.
- No change to `src/vacancy_radar/index/search.py`, `index/build.py`,
  `vault/reader.py`, or `vault/paths.py` behavior; `core.py` imports
  and composes them.
- Downstream: stage 7 (writes) and stage 8 (MCP) will both import
  `core.py`'s functions directly.
