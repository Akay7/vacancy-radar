# Changelog

All notable changes to this project are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/), and this
project uses [Semantic Versioning](https://semver.org/).

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

[0.1.0]: https://github.com/Akay7/vacancy-radar/releases/tag/v0.1.0
