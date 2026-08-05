## Why

`vault-model` (stage 1) defines what a valid vacancy, document, and
company look like and how to parse/serialize one file. Nothing yet
walks an actual vault directory and turns it into an in-memory
collection. Every later stage — index build (diffing snapshots to
decide what to re-embed), retrieval, the CLI, the MCP server — needs a
single, resilient entry point that reads a vault once and hands back a
consistent snapshot, without a single malformed file aborting the
whole read. This stage delivers exactly that: traversal, parsing,
hashing, and vault-path resolution. No index, no embeddings, no
writes.

## What Changes

- Add `src/vacancy_radar/config.py`: `resolve_vault_path()` with
  precedence explicit argument → `VAULT_PATH` env var →
  `VaultNotConfiguredError`. Resolves to an absolute path and verifies
  it exists, is a directory, and contains a `.vacancy-radar/` marker.
  Takes an optional explicit path so a later MCP-roots-based caller
  (stage 8) can pass a client-supplied root without restructuring this
  function.
- Add `src/vacancy_radar/vault/` package: `paths.py` (layout constants
  and `is_within` containment check), `hashing.py` (`content_hash`,
  sha256 of file bytes, never mtime/size/inode), `reader.py`
  (`read_vault` → `VaultSnapshot`, a frozen collection of vacancies,
  documents, companies, hashes, and non-fatal warnings, with derived
  accessors `documents_for`, `vacancies_for`, `last_activity`).
- **Layout correction**: the canonical tree this stage reads is the one
  stage 1's fixture generator actually committed —
  `{vault}/{company_slug}/_company.md` and
  `{vault}/{company_slug}/{vacancy_id}/{vacancy.md, documents/*.md}` —
  not the `vacancies/`-prefixed, `emails/`/`notes/`/`takehome/`-split
  tree originally sketched for this stage. See design.md for the full
  reconciliation; this is a spec correction, not a stage-1 code change.
- Extend `tests/fixtures/generate.py`:
  - `--broken` mode producing the malformed-file, unknown-status,
    duplicate-id, and orphan-directory fixtures this stage's resilience
    tests need, without touching the healthy tree.
  - Write a `.vacancy-radar/` marker directory at the vault root (the
    healthy tree currently has no vault marker at all).
  - Give at least one `takehome`-kind document a non-markdown file
    (e.g. `.pdf`) instead of a `.md` + frontmatter file, so the
    "non-markdown files are registered by path, not parsed" requirement
    has a real fixture to exercise.
  - Add an optional scale override so a test can generate a ~700-vacancy
    vault on demand, without changing the committed fixture's seed or
    size.

## Capabilities

### New Capabilities

- `vault-config`: `VaultPath` resolution precedence, absolute-path
  normalization, vault-marker validation, and the two fatal error
  types (`VaultNotConfiguredError`, `VaultNotFoundError`).
- `vault-layout`: the canonical on-disk tree constants and the
  `is_within` containment check that every read uses to reject path
  traversal and out-of-vault symlinks.
- `content-hashing`: `content_hash` — stable sha256 of file bytes,
  immune to mtime/size/inode changes.
- `vault-reader`: `read_vault` / `VaultSnapshot` — traversal, parsing
  into stage-1 models, non-fatal warning collection, derived
  accessors (`documents_for`, `vacancies_for`, `last_activity`), and
  the resilience guarantee that one malformed file never aborts a read.

### Modified Capabilities

- `fixture-generation`: adds `--broken` mode, a `.vacancy-radar/`
  marker directory in the healthy tree, a non-markdown take-home
  document, and an optional scale override for performance testing.
  The existing byte-identical/seeded-determinism guarantee is
  unchanged and still applies to the healthy tree.

## Impact

- New files: `src/vacancy_radar/config.py`,
  `src/vacancy_radar/vault/__init__.py`,
  `src/vacancy_radar/vault/paths.py`,
  `src/vacancy_radar/vault/hashing.py`,
  `src/vacancy_radar/vault/reader.py`, plus their test modules.
- Modified: `tests/fixtures/generate.py` (additive: `--broken` mode,
  marker directory, one non-markdown document, scale override) and the
  committed `tests/fixtures/vault/` tree (regenerated with the same
  documented seed — every existing file's content is unchanged, one
  new marker directory and one file-extension swap are added).
- No new runtime dependencies. No `lancedb`/`fastembed` imports. No
  index, embedding, chunking, or search of any kind. No writes to the
  vault from any function this stage adds.
- Fixes a latent gap: `Company` (stage 1) had no reader; this stage
  supplies it via `_company.md` parsing.
- Establishes the read path every later stage builds on: getting
  warning semantics or containment wrong here means a corrupted vault
  entry could silently vanish from search results, or a symlink could
  leak reads outside the vault.
