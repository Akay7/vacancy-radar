## Why

`Vacancy.source_url` is currently required — enforced by the model
(`vault-model` spec), threaded as a required parameter through
`core.create_vacancy`, `cli.py`'s `new` command, and the MCP
`create_vacancy`/`find_existing` tools. There's a real case this
excludes: a recruiter emails a PDF with no job-posting URL anywhere.
Today there's no way to track that vacancy at all without inventing a
fake URL to satisfy validation.

## What Changes

- `Vacancy.source_url` becomes `str | None = None`, still validated as
  an http/https URL whenever a value is given.
- `core.create_vacancy`'s signature reorders: `source_url` moves from
  its current required-positional slot (between `role` and
  `found_date`) to sit alongside the function's other optional
  keyword parameters, since Python requires every parameter after a
  defaulted one to also default, and `found_date`/`status` (currently
  after `source_url`) stay required. Every call site
  (`cli.py`'s `new` command, `mcp_server.py`'s `create_vacancy` tool,
  and ~20 positional calls across `tests/test_core.py`) switches from
  positional to keyword arguments in the same pass.
- `core.find_existing`'s `source_url` parameter becomes `str | None =
  None`: a caller with no URL to check against (the recruiter's
  message had none either) can still check for a duplicate by company
  alone. The source_url tier only ever matches on a real, equal,
  non-`None` value — two vacancies that both lack a `source_url` are
  never treated as matching each other because of that absence.
- `cli.py`'s `new` command: `--url` becomes optional.
- The MCP `create_vacancy` tool's `source_url` parameter becomes
  optional; its description gains the recruiter-sent-only-a-PDF
  example and says to call `find_existing` with just `company` when
  there's no URL to check against.
- The MCP `find_existing` tool's `source_url` parameter becomes
  optional, mirroring `core.find_existing`.

No change to `source_url`'s http/https validation when a value is
provided. No change to vacancy-id derivation (already independent of
`source_url`). No change to CLI display (`vacancy-radar show` doesn't
currently render `source_url` at all — a separate, pre-existing gap,
untouched here).

**Process note**: this change stacks on top of two still-unarchived
changes (`mcp-server`, `llm-import`) that already touch
`mcp-write-tools`/`mcp-read-tools`/`vacancy-lookup`/`vacancy-creation`.
The user chose not to archive them first, so this change's delta specs
for those four capabilities are written against the current *merged*
text (mcp-server's original + llm-import's own delta), reconstructed
requirement by requirement — see design.md for exactly which
requirements needed a real edit versus which remain true unchanged.

## Capabilities

### Modified Capabilities

- `vault-model`: `source_url` is no longer in `Vacancy`'s mandatory-
  field list; still rejected when provided with a non-http/https
  scheme.
- `vacancy-creation`: `create_vacancy` accepts an optional `source_url`
  (new requirement, additive on top of llm-import's own delta for this
  capability).
- `vacancy-lookup`: `find_existing`'s `source_url` parameter is
  optional; a new requirement states the None-vs-None non-match rule.
- `mcp-write-tools`: `create_vacancy` tool's `source_url` is optional;
  its description states the recruiter-PDF convention.
- `mcp-read-tools`: `find_existing` tool's `source_url` is optional.

## Impact

- Modified files: `src/vacancy_radar/models.py` (`Vacancy.source_url`),
  `src/vacancy_radar/core.py` (`create_vacancy`, `find_existing`
  signatures), `src/vacancy_radar/cli.py` (`new` command),
  `src/vacancy_radar/mcp_server.py` (`create_vacancy`, `find_existing`
  tools).
- Modified tests: `tests/test_core.py` (~20 existing `create_vacancy`
  calls switched from positional to keyword arguments, plus new
  scenarios), `tests/test_cli.py`, `tests/test_mcp_server.py`.
- No new runtime dependency. No change to id derivation, source_url's
  validation-when-present, or CLI display code.
