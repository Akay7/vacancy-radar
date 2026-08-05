## Context

Stage 1 (`vault-model`) fixed the shape of one vacancy, one document,
one company, and how to parse/serialize one frontmatter file. It
deliberately stopped short of walking a directory. This stage is that
walk: turn a vault directory into an in-memory `VaultSnapshot` that
every later stage (index build, retrieval, CLI, MCP server) reads
from, resiliently enough that one hand-edited file with broken YAML
doesn't take down a read of the other 699.

The stage brief that seeded this change sketched a target tree
(`vacancies/{company_slug}/...` with `emails/`, `notes/`, `takehome/`
split by kind, plus `_archive/` and `_unmatched/`). That tree does not
exist. `tests/fixtures/generate.py`, committed in stage 1 and treated
as ground truth by the "run against the committed fixtures" testing
mandate, writes a different, flatter tree:

```
{vault}/{company_slug}/_company.md
{vault}/{company_slug}/{vacancy_id}/vacancy.md
{vault}/{company_slug}/{vacancy_id}/documents/{doc_id}.md
```

All four `DocumentKind` values (`posting`, `email`, `note`,
`takehome`) live together in one `documents/` directory, distinguished
by frontmatter, not by which subdirectory they're in. There is also no
`vacancies/` prefix and no `_archive/`/`_unmatched/` trees.

This design reconciles the brief against reality by treating the
committed fixture tree as canonical and the brief's sketch as
aspirational. `_archive/` and `_unmatched/` are deferred to whichever
later stage first writes to them (the writer is stage 6; nothing reads
or writes there yet, so inventing their shape now would be
speculative). This was confirmed with the user rather than decided
silently, given how much of the deliverable list it touches.

## Goals / Non-Goals

**Goals:**
- A single `read_vault(path) -> VaultSnapshot` entry point that never
  raises on a malformed *file* — only on a missing/misconfigured
  *vault*.
- Containment safety: nothing this stage reads can escape the vault
  root via `..` or a symlink, and a symlink loop terminates.
- Change detection primitives (`content_hash`) that later stages can
  diff between two `VaultSnapshot`s to decide what to re-embed.
- `VaultPath` resolution with a documented seam for stage 8's
  MCP-roots-based resolution.

**Non-Goals:**
- Any index, embedding, chunking, or search (stage 3+).
- Writing, moving, or deleting anything in the vault (stage 6).
- `_archive/` and `_unmatched/` handling — undefined until a stage
  writes to them.
- MCP roots resolution itself — only the parameter seam for it.
- Restructuring the committed fixture tree's existing file layout.
  Extensions to `generate.py` in this change are additive (a marker
  directory, one non-markdown file, a `--broken` mode, a scale
  override) — no existing fixture file's path or content changes.

## Decisions

**The committed fixture tree is canonical; the brief's sketch is not.**
See Context. Concretely, `paths.py` defines the tree as
`{company_slug}/{vacancy_id}/{vacancy.md, documents/}`, no `vacancies/`
prefix, one `documents/` directory per vacancy holding every
`DocumentKind`. This was one of three options put to the user
(match stage 1 reality / restructure fixtures to the brief's tree /
support both shapes); matching reality was chosen because it's zero
risk to already-committed, already-tested stage-1 fixtures and this
stage's own test mandate runs against those exact fixtures.

**The vault marker is `.vacancy-radar/`, not `vacancies/`.** The brief
offered `.vacancy-radar/` or `vacancies/` as alternative markers;
since the real tree has neither today, `vacancies/` is dropped (it
isn't a real directory in this layout — it was an artifact of the
brief's alternate tree) and `.vacancy-radar/` is kept as the sole
marker. It's added to the healthy fixture tree by this change (empty
directory, vault root only) so `config.py`'s tests have something real
to resolve against. A content-based heuristic ("does it contain at
least one `_company.md`?") was considered and rejected: an empty,
freshly-initialized vault has no companies yet but is still a valid
vault, and a marker directory is unambiguous either way.

**Non-markdown documents are registered inside `documents/`, not a
separate `takehome/` tree.** The brief's "non-markdown files under
`takehome/` are indexed as Documents by path, unparsed" requirement is
still real and still worth keeping — take-home assignments are
genuinely often PDFs or zips — but there's no `takehome/` directory in
this layout. The equivalent, and the one this stage implements: any
non-`.md` file inside a vacancy's `documents/` directory is registered
as a `Document` by path (no frontmatter parse attempted, `kind`
inferred from context or left to a later enrichment stage). This
change extends `generate.py` to give at least one `takehome`-kind
document a real non-markdown file so the scenario has a fixture.

**`VaultSnapshot` is frozen.** Stage 3 (index build) will hold two
snapshots — before and after a vault re-read — and diff them by id to
decide what needs re-embedding. A mutable snapshot makes "did this
change since I captured it" unanswerable without deep-copying
defensively at every call site. Pydantic's `model_config =
ConfigDict(frozen=True)` (already the pattern for stage-1 models,
which use plain immutable dataclass-style construction) gets this for
free: the dicts inside a frozen Pydantic model are still technically
mutable objects, so `VaultSnapshot` additionally exposes only
read-only views (`MappingProxyType`) over `vacancies`, `documents`,
`companies`, and `hashes`, closing that gap. Alternative considered: a
plain frozen `dataclass` with tuples instead of dicts — rejected
because id-keyed lookup (`snapshot.vacancies[id]`) is the dominant
access pattern for every downstream consumer, and converting a tuple
to a dict at every call site to get that is worse than paying for a
`MappingProxyType` wrapper once at construction.

**Hash the full file, not just the body.** Simpler and correct: one
hash function, one code path, no frontmatter-vs-body boundary to keep
in sync with `frontmatter.py`. Consequence: editing only frontmatter
(e.g. flipping `status`) changes the hash and triggers re-embedding
even though the embedded prose (the body) didn't change. Accepted —
at vault scale (hundreds of files, not millions) re-embedding one
file's chunks on a frontmatter-only edit costs milliseconds, and
`status` changes are exactly the kind of edit that should invalidate
any status-derived index fields anyway.

**Warnings are data, not log calls.** `VaultWarning` is a small frozen
model (`kind`, `message`, `path`) collected into
`VaultSnapshot.warnings`. Nothing in `config.py` or `vault/*.py` calls
`print`, `logging`, or writes to stderr — `vacancy-radar doctor`
(a later stage) is the sole renderer. This keeps `read_vault` usable
from the MCP server (stage 9), where stray stdout output would corrupt
JSON-RPC framing (see the project's architectural invariant #5) and
keeps the reader trivially testable — a test asserts on
`snapshot.warnings`, not on captured output.

**Duplicate vacancy ids: keep one deterministically.** When two
`vacancy.md` files parse to the same `id`, the snapshot keeps the one
whose path sorts first (`sorted()` on the string path), and the
warning names both paths. Deterministic tie-breaking (rather than
"first encountered in `os.walk` order", which depends on filesystem
iteration order and isn't guaranteed stable across platforms) makes
the resulting snapshot reproducible for a given vault state,
independent of directory-entry ordering.

**`is_within` resolves both paths before comparing, and walks
symlinks with a visited-set guard.** Containment is checked via
`Path.resolve()` on both the candidate and the vault root, then
`is_relative_to`. Directory traversal (`os.walk`/`Path.rglob`) tracks
each directory's resolved real path in a `set` before descending into
it; a repeat means a symlink loop, and that branch is skipped rather
than recursed into. This is the same technique used to defend against
zip-slip-style traversal in other contexts, adapted to a walk instead
of an archive.

**The MCP-roots seam in `config.py`.** `resolve_vault_path(explicit:
Path | str | None = None) -> Path` takes the explicit path as its
first parameter today, used by the CLI and by tests. Stage 8 adds a
second caller that resolves an MCP client's root and passes it as
`explicit` — no signature change, no restructuring. This is called out
explicitly rather than implemented because stage 8 also needs to
decide *which* of possibly several client-supplied roots to use, which
is out of scope here.

**Performance test generates its own oversized vault, out-of-band from
the committed fixture.** `generate_vault` gains optional
`min_companies`/`max_companies` override parameters (defaulting to the
existing `MIN_COMPANIES`/`MAX_COMPANIES` module constants, so the
documented-seed committed fixture is byte-for-byte unaffected). The
performance test calls `generate_vault` with overrides sized to
produce ~700 vacancies into a temp directory, not into
`tests/fixtures/vault/`.

## Risks / Trade-offs

- [Treating the committed fixture tree as canonical means the brief's
  richer `emails/`/`notes/`/`takehome/`/`_archive/`/`_unmatched/` tree
  is unimplemented] → Nothing currently produces that tree; building
  readers for directories nothing writes to is speculative. If a later
  stage needs that split (e.g. to let a human `ls` just the emails),
  it can be introduced as its own change with its own migration of the
  committed fixtures.
- [`MappingProxyType` wrapping adds a small indirection over plain
  dicts] → Negligible at vault scale; the alternative (trusting every
  caller not to mutate a shared dict) is the kind of "worked until it
  didn't" bug stage 3's diffing is specifically vulnerable to.
- [Hashing full files means frontmatter-only edits trigger
  re-embedding] → Documented above; accepted as cheap at this scale.
- [Symlink-loop guard adds a visited-set check on every directory
  descent] → O(1) set lookup per directory, irrelevant next to
  frontmatter parsing cost.
- [`.vacancy-radar/` marker requires regenerating the committed fixture
  tree] → Additive only (one new empty directory, one file extension
  swap for the non-markdown take-home case); every existing file's
  path and byte content is unchanged, verified by diffing the
  regenerated tree against the current one before committing.

## Migration Plan

Read-only stage, no runtime migration. The one "migration" is
regenerating `tests/fixtures/vault/` with the same documented seed
after extending `generate.py`, and diffing against the currently
committed tree to confirm only the intended additions appear.

## Open Questions

None outstanding. The layout mismatch was the one open question and
was resolved with the user before this design was written (see
Context and the first Decision).
