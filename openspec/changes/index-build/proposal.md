## Why

The vault (stage 1) and reader (stage 2) give us a validated, in-memory
view of every vacancy and document, but nothing turns that into
something searchable. Retrieval (stage 4) needs a hybrid BM25 + vector
index to query against; this stage builds and incrementally maintains
that index, including extracting searchable text out of non-markdown
sources (PDFs today) via a git-tracked sidecar convention, so the
index itself can be deleted and rebuilt at any time without losing
anything.

## What Changes

- Add `src/vacancy_radar/index/extract.py`: `extract_to_sidecar` for
  PDF sources via `pypdf` — encrypted/malformed/scanned PDFs write an
  empty sidecar plus a warning rather than raising; a sidecar marked
  `manually_corrected: true` is never regenerated. Non-PDF sources
  (code, archives, anything else) get no sidecar at all in this stage.
- Add `src/vacancy_radar/index/schema.py`: the one-row-per-document
  LanceDB table schema, denormalized vacancy fields included, vector
  dimensionality read from the configured embedding model rather than
  hardcoded.
- Add `src/vacancy_radar/index/embed.py`: a lazily-loaded, per-model
  cached `fastembed` wrapper (`embed_texts`) — not loaded at import
  time.
- Add `src/vacancy_radar/index/build.py`: `build_index` — diffs a
  `VaultSnapshot`'s content hashes against the table, embeds only
  what's new or changed, refreshes denormalized columns on unchanged
  rows without re-embedding them, deletes rows for vanished sources,
  (re)builds the FTS index, and returns an `IndexReport`.
- Add `src/vacancy_radar/index/store.py`: index handle resolution
  keyed by vault path, created lazily on first use — never a
  module-level singleton, since stage 8 can switch vaults at runtime.
- **Reader amendment (MODIFIED delta on `vault-reader`)**: the stage 2
  reader currently treats every `.md` file under a `documents/`
  directory as an independent `Document` and tries to parse it with
  that schema. A sidecar (e.g. `spec.pdf.md`) has a different
  frontmatter shape entirely (`extracted_from`, `source_hash`,
  `extractor`, `extracted_at`, `manually_corrected`), so today it would
  fail `Document` validation and produce a spurious `invalid_document`
  warning for every sidecar in the vault. This change teaches the
  reader to recognize a sidecar by its frontmatter shape (presence of
  `extracted_from`) and exclude it from `documents` — the file it
  shadows is already registered as the `Document` via the existing
  non-markdown path. Two new failure modes are added: an orphaned
  sidecar (its source no longer exists) and a mismatched sidecar (its
  `extracted_from` disagrees with its own filename) each produce a new
  warning kind and are excluded.
- **Layout addition (ADDED delta on `vault-layout`)**: new path helpers
  for the sidecar naming convention (`sidecar_path_for`), used by the
  extractor to know where to write.
- **Extractor eligibility reconciliation**: the brief describes
  eligibility as "PDFs get sidecars; code and archives under
  `takehome/` don't." Stage 2 shipped a flatter layout than the one
  the brief assumed — there is no `takehome/` subdirectory; every kind
  of document (including take-homes) lives in one `documents/` folder,
  distinguished by `DocumentKind`, not by path. This change makes
  eligibility extension-based instead of path-based: only `.pdf` files
  are extraction candidates, anywhere under `documents/`. Every other
  extension (including `.py`, `.zip`, and — not yet implemented —
  `.docx`) gets no sidecar and indexes by filename only. This is
  equivalent in every case the brief specifies and needs no
  `takehome/`-specific logic. See design.md for the reasoning.
- Add three new runtime dependencies: `lancedb`, `fastembed`, `pypdf`
  (all explicitly pre-approved). No others — no `torch`, no
  `sentence-transformers`, no reranker.

## Capabilities

### New Capabilities

- `sidecar-extraction`: `extract_to_sidecar` — PDF text extraction into
  a git-tracked markdown sidecar, its frontmatter, its regeneration
  rules (hash-gated, never overwriting a manual correction), and its
  failure modes (encrypted, malformed, scanned/empty).
- `index-schema`: the LanceDB table shape — one row per document (no
  chunking), denormalized vacancy fields, vector dimensionality driven
  by the active embedding model.
- `embedding`: lazy, per-model-name cached `fastembed` loading and
  batched `embed_texts`.
- `index-build`: `build_index` and `IndexReport` — incremental
  diffing by content hash, denormalized-column refresh without
  re-embedding, deletion of rows for vanished sources, FTS
  (re)creation, `force` full rebuild, and the disposability guarantee
  this stage exists to prove.
- `index-store`: lazy, vault-path-keyed index handle resolution.

### Modified Capabilities

- `vault-reader`: sidecar files (frontmatter containing
  `extracted_from`) are recognized and excluded from `documents`
  instead of failing validation as malformed `Document`s. Two new
  warning kinds — orphaned sidecar, mismatched sidecar — are added for
  the cases where a sidecar's claim about its source doesn't hold up.
- `vault-layout`: adds `sidecar_path_for(source_path)`, the single
  place the `{source-filename}.md` naming convention is expressed, so
  the extractor and any future caller derive it the same way.

## Impact

- New files: `src/vacancy_radar/index/__init__.py`,
  `extract.py`, `schema.py`, `embed.py`, `build.py`, `store.py`, plus
  their test modules.
- Modified: `src/vacancy_radar/vault/reader.py` (sidecar recognition),
  `src/vacancy_radar/vault/paths.py` (sidecar path helper),
  `tests/fixtures/generate.py` (adds real, synthetic PDF fixtures —
  valid, malformed, encrypted, and scanned/text-free — needed to
  exercise extraction; the existing fake-bytes take-home placeholder
  from stage 2 is unaffected).
- New runtime dependencies: `lancedb`, `fastembed`, `pypdf`.
- New on-disk artifacts: the `.index/` directory at the vault root
  (already gitignored since the skeleton stage, already treated as an
  internal/skipped directory by the reader) holds the disposable
  LanceDB table; sidecar `.md` files are written *inside* the vault,
  git-tracked, next to the source they describe.
- This stage writes to the vault for the first time — but only
  sidecars, gated behind an explicit flag, never touching a source
  file or deleting anything. Every other write (vacancies, documents)
  remains stage 6's job.
- No query path, ranking, CLI surface, or MCP surface — stage 4 and
  later.
