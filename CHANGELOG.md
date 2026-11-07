# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/), and this
project uses [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-11-08

### Added

- **Inline views for the MCP server (MCP Apps).** The server registers
  the `io.modelcontextprotocol/ui` extension and ships four
  self-contained `ui://` HTML views, so a host that supports MCP Apps
  renders `list_vacancies`, `get_vacancy`, `get_company`, and `search`
  results as a card or table instead of raw JSON. The views make no
  network request and render only fields already present in the tool's
  result; there is nothing to configure, and a client that has not
  negotiated the extension sees the same text output as before.

- **Resume A/B tracking.** A vacancy can record which resume variant
  you applied with — a short label such as `backend-v2` — via
  `--resume` on `new`, `status set`, and `edit` (and the matching
  `create_vacancy`, `set_status`, `edit_vacancy` MCP arguments).
  `list --resume` / `list_vacancies(resume=...)` filter by it, and the
  new `vacancy-radar resumes` command and `resume_stats` MCP tool
  compare variants by application count, current status, and advance
  rate. Existing vaults need no migration; applications without a
  resume are reported on their own row.

### Fixed

- **MCP tool calls no longer time out after writes or reindexing.** Tools
  ran blocking vault and index work directly on the server's event
  loop, so the whole server stopped responding while a write reindexed.
  They now run in worker threads, with no lock between them.

- **Several Claude/opencode instances and the CLI can write to one
  vault at the same time.** New notes, documents, and vacancies can no
  longer overwrite a file another writer created a moment earlier; the
  later one gets the next free name or id. `set_status` and
  `edit_vacancy` refuse to overwrite a `vacancy.md` that changed after
  they read it (`ConcurrentModificationError`; call again). A write no
  longer fails when its index refresh collides with another writer's:
  the refresh retries, and if it still can't finish, the write
  succeeds, a warning is logged, and `search` reports the index as
  stale until the next reindex. Two limits remain: two changes to the
  *same* vacancy at the same instant can still lose one of them, and
  two overlapping `add_document` calls with the same `external_id` can
  both file a copy.

- opencode printed `unknown format "path" ignored in schema at path
  "#/properties/result"` on every start. `append_note` and
  `add_document` returned a `Path`, which FastMCP advertises as the
  non-standard JSON Schema format `path`; they now return the path as a
  plain string (same value on the wire).
- The `mcp-transport` spec's tool-list requirement said "eleven tools"
  and omitted `edit_vacancy`; corrected to twelve to match the server
  and its tests.

## [0.2.0] - 2026-08-11

Vacancies became editable: their fields, not just their status, with
every edit recorded in the vault.

### Added

- **Editing a vacancy's fields**, not just its status: `vacancy-radar
  edit` and the `edit_vacancy` MCP tool set `source_url`, `role`,
  `stage_note`, `salary_note`, `recruiter`, `external_id`, `tags`,
  `found_date`, and `applied_date` in one validated, atomic write.
  Nullable fields are removed with `--clear`/`clear`; `--tags` replaces
  the whole list. Status stays with `status set` (which validates the
  transition), and a vacancy's company and id remain immutable.
- **Edit history.** Every applied edit appends `- <date>: <field>: <old>
  -> <new>` to a `## Edit History` block in `vacancy.md`, so an
  overwritten frontmatter value still leaves an append-only record in
  the vault. A call that would change nothing writes nothing.

### Changed

- Status- and edit-history entries are now appended inside their own
  section rather than at the end of the body, so the two blocks can
  coexist in any order. Output for a file whose last section is
  `## Status History` is unchanged.

### Fixed

- **A company name now works as a write command's vacancy argument.**
  `note`, `status set`, `edit`, and `add` documented that a vacancy
  could be named by company or fuzzy match, but every company-tier
  match was rejected as "resolved to a company, not a vacancy". A
  company holding exactly one vacancy now resolves to it, via the new
  `core.resolve_vacancy`; one holding several still refuses, naming
  every candidate id. `core.resolve` itself is unchanged, so `show` and
  the read tools still answer a company query with a company.

## [0.1.0] - 2026-08-10

First release: a local-first job application tracker built around a
markdown vault, with hybrid search and an MCP server.

### Added

- **Vault model and reader.** A markdown vault is the source of truth —
  typed frontmatter, stable derived ids, company and vacancy documents,
  and a reader that collects warnings rather than failing on a single
  malformed file. `vacancy-radar init` creates or idempotently adopts a
  vault directory without touching existing content.
- **Derived LanceDB index.** Chunked documents with BM25 and vector
  columns, rebuilt from the vault by `vacancy-radar reindex`; every
  write reindexes its own effect eagerly, so results are searchable
  immediately.
- **Hybrid retrieval.** Keyword, semantic, and hybrid search modes with
  configurable fusion. The shipped defaults — linear-combination fusion
  at `vector_weight` 0.5 — were chosen from measurement, reversing the
  design's original RRF guess.
- **Evaluation harness** (`vacancy-radar eval`): 30 labelled queries
  across seven categories scored with recall@k and MRR against the
  committed fixture vault. See [docs/evaluation.md](docs/evaluation.md).
- **Read CLI**: `list`, `show`, `search`, and `doctor`, each with a Rich
  table for humans and a stable `--json` shape for piping.
- **Write CLI**: `new`, `note`, `status set`, `add`, and `reindex`.
  Every write is append-only or a validated status transition; there is
  no delete command anywhere in the CLI.
- **PDF sidecar extraction** (`reindex --extract-sidecars`): extracts
  text from PDFs under `documents/` into git-tracked `.pdf.md`
  sidecars, so they are searchable by content. An encrypted or
  unparseable PDF warns and is skipped rather than failing the reindex.
- **MCP server** (`vacancy-radar-mcp`): eleven tools matching `core.py`
  one for one, two resources, and three prompts, over stdio for any MCP
  client. Typed errors surface as structured results a calling model
  can act on, never a crash.
- **Conversational import** via `find_existing` + `create_vacancy`, for
  moving an existing tracker into a vault by talking to a model. See
  [docs/import-guide.md](docs/import-guide.md).
- **Published to PyPI.** `uvx vacancy-radar` and `uv tool install
  vacancy-radar` expose the CLI, and `uvx --from vacancy-radar
  vacancy-radar-mcp` the MCP server — no clone and no `uv.lock`
  required. The distribution carries full landing-page metadata and an
  SPDX `MIT` license expression, with the LICENSE file shipped in both
  the wheel and the sdist.
- **Release automation** (`.github/workflows/release.yml`): a
  tag-triggered release that builds once, verifies the built wheel by
  installing and running it in a clean environment with no repository
  checkout, and only then uploads it via PyPI Trusted Publishing. No
  index credential is stored anywhere. A `workflow_dispatch` input runs
  the same chain against TestPyPI as a dry run. See
  [docs/releasing.md](docs/releasing.md).
- **Packaging test** (`tests/test_packaging.py`): asserts the built
  distribution's entry points, license file, and landing-page metadata
  on every test run, so a packaging regression fails CI instead of
  degrading a release.
- CI on pushes to `main` and pull requests: pre-commit hooks and the
  full test suite, with the embedding model cached by model name.

[0.3.0]: https://github.com/Akay7/vacancy-radar/releases/tag/v0.3.0
[0.2.0]: https://github.com/Akay7/vacancy-radar/releases/tag/v0.2.0
[0.1.0]: https://github.com/Akay7/vacancy-radar/releases/tag/v0.1.0
