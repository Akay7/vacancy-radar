## Context

Stage 2 gives us `read_vault(path) -> VaultSnapshot`: vacancies,
documents, companies, per-file content hashes, all in memory. This
stage turns that into a queryable LanceDB table — one hybrid index
combining BM25 full-text and vector search, rebuildable from nothing
but the vault at any time. Retrieval itself (stage 4) is out of scope;
this stage only builds and incrementally maintains the index.

Two things this stage introduces that didn't exist before:

1. **The sidecar convention.** Non-markdown sources (PDFs today) have
   no text a `Document` row can embed. A sidecar — a markdown file
   living beside the source, named with the source's full filename
   plus `.md` — holds that extracted text, is git-tracked like
   everything else in the vault, and can be hand-corrected once and
   stay correct forever.
2. **The first vault write.** Every prior stage was read-only. This
   stage writes sidecars — nothing else, and only behind an explicit
   flag.

## Goals / Non-Goals

**Goals:**
- A `build_index` that is safe to run repeatedly and safe to delete
  the output of: `.index/` is fully disposable, reconstructible from
  the vault plus (deterministic) re-embedding.
- Incremental rebuilds that only pay embedding cost for what actually
  changed, while still keeping denormalized columns (status, company,
  ...) in sync on every build.
- PDF text extraction that never raises, never silently loses a human
  correction, and never gets re-run needlessly.
- An embedding wrapper that costs nothing until the first real search
  or build actually needs it.

**Non-Goals:**
- Any query, ranking, or retrieval logic (stage 4).
- Chunking below the document level (see Decisions).
- `.docx` or any extractor beyond PDF (the sidecar naming convention
  anticipates it; nothing here implements it).
- OCR for scanned PDFs — a human fills the sidecar body by hand.
- A CLI or MCP surface for triggering a build or extraction (stages
  8–9). `build_index`/`extract_to_sidecar` are library functions only.

## Decisions

**Extraction eligibility is extension-based (`.pdf` only), not
path-based.** The brief frames eligibility around a `takehome/`
subdirectory ("code and archives under `takehome/` get no sidecar").
Stage 2 shipped a flatter layout than that — every document kind
(posting, email, note, takehome) lives in one `documents/` folder,
distinguished by `DocumentKind` in frontmatter, not by which
subdirectory it's in (see stage 2's design.md for why). There is
consequently no `takehome/` path to gate on. The equivalent rule that
needs no such path: `extract_to_sidecar` attempts extraction only for
files with a `.pdf` suffix, anywhere under `documents/`; every other
extension — `.py`, `.zip`, `.docx` (not yet implemented), plain
`.txt`, anything — gets no sidecar and indexes by filename only. This
produces identical behavior to the brief's rule for every case the
brief actually lists (PDFs get sidecars; code and archives don't) and
requires no directory-shape assumption that doesn't hold.

**Sidecar detection is frontmatter-shaped, not filename-shaped.** The
naive rule — "a `.md` file is a sidecar if a sibling file exists named
the same minus the trailing `.md`" — has a real ambiguity: an ordinary
`Document`'s `.md` filename (a generated doc id, e.g.
`2022-03-22-acme-corp-backend-engineer-doc1.md`) could theoretically
collide with a coincidental sibling of that exact name with no
extension. Instead, the reader treats a `.md` file as sidecar-shaped
if its parsed frontmatter contains an `extracted_from` key — a field
that only ever appears in sidecar frontmatter, never in `Document`
frontmatter. This is checked *before* attempting `Document(**metadata)`
validation, so a sidecar never reaches (and never fails) that
validation path. Given `extracted_from`, the reader then:
- looks for a sibling file named exactly `extracted_from`'s value; if
  it's missing, the sidecar is orphaned — warning, excluded;
- if `extracted_from` doesn't match the sidecar's own filename (minus
  the trailing `.md`), the sidecar is mismatched — warning, excluded;
- otherwise, the sidecar silently shadows its source and contributes
  no `Document` of its own. The source file is already registered as
  a `Document` by the existing non-markdown path — unchanged.

**Construction (the extractor) is path-driven; detection (the reader)
is frontmatter-driven.** `vault/paths.py` gains
`sidecar_path_for(source_path) -> Path`
(`source_path.with_name(source_path.name + ".md")`) as the one place
the naming convention is expressed, used when *writing* a sidecar. The
reader doesn't need it — it discovers sidecars by frontmatter shape,
as above — but keeping the naming convention in one function means
extractor and any future caller (a `doctor` command, a migration)
derive the same path the same way.

**The vacancy itself gets a row (recommended in the brief); its text
is frontmatter-only, not the vacancy.md body.** A `Vacancy` has no
`Document` of its own today, so its `stage_note`, `salary_note`,
`role`, and `tags` are otherwise unsearchable, and a vacancy with zero
documents would be invisible to search entirely. Its row's `text` is
composed from `role`, `company`, `status`, `stage_note`, `salary_note`,
`recruiter`, and `tags` — not `vacancy.md`'s markdown body. The body
the fixture generator writes is a single redundant title line (`# {role}
at {company}`); requiring it here would mean adding a `body` field to
stage 1's frozen `Vacancy` model for content that carries no
information beyond what's already in frontmatter. `doc_id` for a
vacancy row is `f"vacancy:{vacancy.id}"` (namespaced so it can never
collide with a real document id) and `kind` is the literal `"vacancy"`
— a sentinel outside `DocumentKind`'s vocabulary, since this row
doesn't correspond to a `Document` at all. Its `content_hash` and
`path` are the vacancy's own `vacancy.md` hash and path, so an edit to
any frontmatter field — including a bare status change — is exactly
what invalidates and re-embeds it.

**Chunking: none, ever, at this scale.** A document is the semantic
unit — splitting an email strands the signature from the ask, and
splitting a vacancy's stage note from its role makes neither
retrievable on its own. `bge-small-en-v1.5` handles up to 512 tokens;
the fixture corpus's longest document (an email or note, a few
sentences) is nowhere near that. This stops being the right call once
individual documents (a long take-home spec, a multi-page PDF)
routinely exceed the model's context — that's a future stage's
problem, informed by real documents this one doesn't have yet, not a
speculative chunker built ahead of need.

**Sidecars over index-only extracted text.** Storing extracted text
only in the LanceDB row would violate the disposability invariant this
stage exists to prove: delete `.index/`, and every PDF's text — the
expensive part, plus any human correction of a scanned PDF's empty
extraction — is gone, unrecoverable without re-running extraction
against files that might no longer parse the same way (a
`manually_corrected` fix has no source-side representation to
regenerate from). A sidecar is a normal git-tracked vault file: it
survives an index wipe, it's greppable and diffable like everything
else in the vault, and a human who fixes a scanned PDF's empty
sidecar once fixes it forever, not until the next reindex.

**`pypdf`, not `pymupdf`.** `pymupdf` is faster and better at
preserving layout, but it's AGPL-licensed; this project is MIT, and
AGPL's copyleft terms are incompatible with that. `pypdf` is
BSD-licensed and sufficient for plain text extraction — no layout
fidelity is needed for embedding.

**`content_hash` stored per row, keyed to the row's own source.** A
document row's `content_hash` is its source file's hash from
`snapshot.hashes` (for a PDF, the *source* PDF's hash, not the
sidecar's — the sidecar's hash governs whether extraction re-runs, a
separate, upstream decision in `extract.py`, not `build_index`'s
diffing). Storing it inline means `build_index` diffs by reading the
table, not a side file — the index stays self-describing, and a
`force=True` rebuild needs no external bookkeeping to decide it's
starting from nothing.

**Denormalized-field refresh is decoupled from re-embedding.** A
vacancy's own row re-embeds on any frontmatter change (its `text` is
frontmatter-derived, so its `content_hash` — tied to `vacancy.md` —
always changes too). Its *documents'* rows do not: their `content_hash`
is tied to their own file, unchanged by a sibling frontmatter edit.
But their denormalized `status`, `company`, `company_slug`, `tags`,
`applied_date`, `last_activity` columns must still reflect the new
state, or a status-filtered query in stage 4 would show a document
under a stage the vacancy no longer holds. `build_index` therefore
does two passes over vacancies whose hash changed: an embed-and-write
for the vacancy's own row, and a cheap column-only update (no
embedding, no `content_hash`/`text`/`vector` touch) for every sibling
document row. `IndexReport` counts the latter under `unchanged` — the
embedding-relevant state (hash, vector) is unchanged — while the
metadata sync still happens as a side effect.

**`IndexReport`'s `skipped` count is for build-time failures, not
extraction failures.** A document whose source file existed in the
snapshot but is gone by the time `build_index` reads it (a race
between snapshotting and building, or a file deleted mid-run) is
skipped — not embedded, not written, a warning recorded — rather than
crashing the build. Extraction failures (encrypted/malformed/scanned
PDFs) are not build-time skips: they still produce a row, indexed by
filename/title text, same as any source with no sidecar.

**Embedding: lazy, per-model-name cache, no eager import cost.**
`embed.py` holds a private `dict[str, TextEmbedding]` populated on
first `embed_texts` call for a given model name and reused after.
Nothing in `embed.py` or `build.py` instantiates a model at import
time — stage 8 imports this module on every MCP client start, and most
sessions never search, so paying `fastembed`'s ONNX-model load cost at
import would be pure waste on the common path. Vector dimensionality
is read from the loaded model (`fastembed` exposes it), never
hardcoded — `schema.py`'s table-creation takes `vector_dim: int` as a
parameter, so changing `EMBEDDING_MODEL_NAME` and rebuilding produces
a table with the new model's dimensionality with no migration step,
since a `force=True` rebuild (or any build against an empty/absent
index) creates the table fresh against whatever dimension the
currently configured model reports.

**`fastembed` model caching and CI.** `fastembed` downloads its ONNX
model via `huggingface_hub`, which caches to `~/.cache/huggingface/hub/`
by default (overridable via `TextEmbedding`'s `cache_dir` parameter)
and reuses that cache on every subsequent load — offline after the
first successful download, keyed by model name (confirmed empirically:
~8s first load including download, ~0.15s on a cached second load). A
fresh clone's first embedding call requires network access once; after
that, every load — including every subsequent test run — is local.
Tests that exercise the real model are marked `@pytest.mark.embedding`
(registered in `pyproject.toml`); CI caches `~/.cache/huggingface`
keyed by `EMBEDDING_MODEL_NAME` across runs, so the network fetch
happens once per model version, not once per test.

**`store.py`: a plain dict keyed by resolved vault path, not a
singleton.** `get_index_handle(vault_path) -> IndexHandle` looks up (or
lazily creates) a handle in a module-level `dict[Path, IndexHandle]`.
A handle bound at import time, or a single global handle, would
silently keep querying/writing the first vault's table after stage 8
switches vaults via MCP roots. Keying by resolved path (not the raw
argument) means two different-looking paths to the same vault resolve
to the same cached handle.

**PDF test fixtures are generated programmatically, not committed as
binary blobs.** This stage needs a valid PDF (successful extraction),
a malformed one (corrupt/truncated bytes), an encrypted one, and a
"scanned" one (a real, parseable PDF with no extractable text layer —
e.g. one page containing only an embedded image). All four are built
at test time via `pypdf.PdfWriter` (and, for the encrypted case,
`PdfWriter.encrypt`) into `tmp_path`, matching this project's existing
preference for seeded/generated fixtures over committed binary assets
(see stage 1's fixture generator). None of these become part of the
committed `tests/fixtures/vault/` tree — they're constructed inside
the tests that need them, or via a small shared helper module
(`tests/fixtures/pdfs.py`) if reused across several test files. Stage
2's existing take-home placeholder (arbitrary non-PDF bytes with a
`.pdf` extension) is untouched; it exercises "non-markdown file
registered by path," not extraction, and continuing not to be a real
PDF is fine for that purpose.

## Risks / Trade-offs

- [Extension-based eligibility (`.pdf` only) diverges textually from
  the brief's `takehome/`-based description] → Behaviorally equivalent
  for every case the brief lists; documented above and in proposal.md
  as a reconciliation, the same posture taken for stage 2's layout
  mismatch.
- [Frontmatter-shape sidecar detection means a hand-written `.md` file
  that happens to include an `extracted_from` key gets treated as a
  sidecar even if a human meant it as a real note] → Accepted: nothing
  in the vault format reserves `extracted_from` for machine use only,
  but the convention is documented, and misuse produces a visible
  orphan/mismatch warning rather than silent data loss.
- [Vacancy rows' text excludes `vacancy.md`'s body] → Accepted; the
  body currently carries no information the frontmatter fields don't
  already have. If a future stage starts writing meaningful body
  content, revisit — likely as a `vault-model` MODIFIED delta adding a
  `body` field, not a silent change here.
- [Programmatically generated PDF fixtures, not committed binaries] →
  Slightly more test setup code per suite; avoids binary diffs and
  matches the project's fixture philosophy. `pypdf.PdfWriter` is
  already a dependency for extraction, so no new dependency is needed
  to also generate test PDFs with it.
- [First embedding call on a fresh clone needs network access] →
  Unavoidable for any real embedding model; mitigated by caching
  (local after first run) and by every build/query path not requiring
  embedding unless real search or a build actually runs.

## Migration Plan

Greenfield within this stage — no existing index to migrate.
Regenerating `tests/fixtures/vault/` is not required by this stage
(no committed fixture changes to the healthy tree); PDF fixtures are
generated at test time, not committed.

## Open Questions

None outstanding. The `takehome/`-vs-flat-layout and sidecar-detection
ambiguities were resolved above, following the same reconciliation
posture used in stage 2 rather than re-blocking on user input for a
structurally identical situation.
