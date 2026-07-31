# Phase 0 Research: Ingestion CLI

No open `NEEDS CLARIFICATION` markers remain in the Technical Context (all resolved directly
from the existing scaffold — `pyproject.toml`, `embedder.py`, `compat.py`, `retriever.py`,
README). The items below are the design decisions needed to move from spec → data model, made
by reading the existing stubs' docstrings as load-bearing intent rather than decorative comments.

## Decision: Chroma access pattern

**Decision**: A thin `ChromaStore` wrapper around `chromadb.PersistentClient(path=".cache/chroma")`
exposing `get_or_create_collection(name)`, `upsert(collection, ids, documents, metadatas)`,
`delete(collection, ids)`, and `count(collection)`. No direct `chromadb` calls elsewhere.

**Rationale**: `retriever.py` already names `.cache/chroma` as the path and `experience_bullets`
/ `vacancies` as the two collections; centralizing access keeps `ingest.py`, `retriever.py`
(M3), and `reindex` (delete-and-rebuild) all pointed at one client configuration instead of
three independent instantiations that could drift.

**Alternatives considered**: Calling `chromadb` directly from `ingest.py` — rejected, since
`reindex` (delete cache dir) and `sync` (per-collection upsert) both need the same client
lifecycle, and a future `/similar`/`/analyze` retrieval path (M3/M4) will need the same
collections without duplicating connection setup.

## Decision: Staleness manifest for `sync`

**Decision**: A local JSON manifest at `.cache/ingest-manifest.json` mapping each source file's
relative path → `{content_hash, chunk_ids}`. `sync` recomputes each file's hash, re-embeds and
upserts only files whose hash changed or that are new, and updates the manifest entry. The
manifest itself is regenerable (deleted by `reindex` along with the Chroma store).

**Rationale**: `ingest.py`'s existing docstring specifies exactly this — "a lightweight
per-file hash cache (local to this module, not user-facing)" — this research confirms JSON-on-disk
as the concrete format and fixes its location alongside `.cache/chroma` so `reindex`'s
"delete the local cache and rebuild" (FR-005) needs only one directory removed, not two
different stores to keep in sync.

**Alternatives considered**: Storing hashes as Chroma metadata on each chunk and querying them
back — rejected as an unnecessary round-trip through the vector store just to answer "did this
file change," and it would entangle staleness bookkeeping with retrieval metadata.

## Decision: Vacancy folder chunking strategy

**Decision**: Reuse `langchain-text-splitters` (already a dependency) per `doc_type`:
`vacancy.yaml` → one chunk (the whole record, rendered as text) tagged `doc_type=vacancy_meta`;
each file under `sources/` → one chunk per file tagged `doc_type=posting` (postings are short;
splitting isn't needed at this scale per Constitution IV); each file under `correspondence/` →
one chunk per file tagged `doc_type=correspondence`; `analysis.md` (if present) → one chunk
tagged `doc_type=analysis`. All four carry company/position/date/outcome metadata copied from
the folder's `vacancy.yaml` (FR-003).

**Rationale**: matches `retriever.py`'s documented filter use-case — "`/similar` can e.g. filter
to `doc_type=posting` only for duplicate-JD detection without pulling in correspondence" — which
only works if each doc type is tagged and separately queryable. One chunk per file is the
simplest scheme that satisfies that filter and matches Constitution IV (don't build
finer-grained splitting than the current scale needs); revisit only if a posting/correspondence
file turns out to regularly exceed the embedding model's context window.

**Alternatives considered**: Splitting every file into fixed-size overlapping chunks regardless
of type — rejected for now as unnecessary complexity at current data volumes (Constitution IV);
can be layered in later behind the same `ChromaStore.upsert` contract without changing the CLI
surface.

## Decision: CV bullet chunking & upsert

**Decision**: Parse `CV_DIR`'s markdown into one chunk per top-level bullet (`- ...` / `* ...`
list item). On every `ingest`/`sync` run, delete all existing entries in the
`experience_bullets` collection and re-insert the full current set (full-replace, per clarified
FR-012) — no manifest entry, no per-bullet id stability required.

**Rationale**: directly implements the resolved clarification (Q3 → full replace); avoids
inventing a stable-id scheme for bullets that would only pay off if `CV_DIR` were large or
changed often, which the Assumptions section explicitly says it isn't.

**Alternatives considered**: Natural-key-per-bullet (e.g., hash of bullet text) with the same
incremental staleness manifest as vacancies — rejected per the clarified answer; adds
bookkeeping with no measurable benefit at this scale.

## Decision: `vacancy.yaml` minimum schema

**Decision**: Add `VacancyRecord` to `models.py` (Pydantic) requiring `company: str`,
`position: str`, `date: date`, `outcome: str`, plus `model_config = ConfigDict(extra="allow")`
so any additional private-schema fields (per the README's "full schema... in the maintainer's
private project plan") pass through without validation errors.

**Rationale**: `retriever.py`'s metadata contract (doc_type/company/position/date/outcome) fixes
the minimum required fields regardless of what else a user's private schema defines; `extra="allow"`
means this feature doesn't need to know or enforce the rest of that private schema to ingest
correctly (per spec Assumptions).

**Alternatives considered**: A strict schema enumerating every known field — rejected, the full
schema is explicitly out of this repo/spec's reach, and a strict model would reject valid user
data the maintainer's private notes define but this codebase doesn't know about.

## Decision: Natural-key folder validation

**Decision**: Validate vacancy folder names against `^\d{4}-\d{2}-\d{2}_[a-z0-9-]+_[a-z0-9-]+$`
(date_company-slug_position-slug). A folder failing this pattern, or whose `vacancy.yaml` is
missing/unparseable/missing a required field, is recorded as invalid (FR-008) and skipped, not
fatal to the run.

**Rationale**: directly matches the naming convention documented in the README and restated in
the spec's Assumptions; a regex is the simplest possible validation (Constitution IV) and gives
a precise, quotable reason for FR-008/SC-004's "clear reason" requirement.

**Alternatives considered**: Parsing the date with `datetime.strptime` and only regex-checking
the slugs — equivalent in practice; regex chosen since it also naturally rejects extra
underscores/segments in one pass and is easy to unit test with clear pass/fail fixtures.

## Decision: Compat-stamp integration

**Decision**: `ingest` and `sync` both check `compat.needs_reindex(stored_stamp)` before doing
incremental work (reading `stored_stamp` from the manifest file); if the embedding model or
schema version stamp has changed since the last run, the command performs a full reindex
automatically instead of a partial sync, then proceeds normally, and writes `CURRENT_STAMP`
into the manifest afterward.

**Rationale**: `compat.py` already exists with exactly this stated purpose — "triggers an
automatic reindex on embedding-model or schema mismatch, instead of silently serving stale
results" — wiring it in is required to make good on that module's own contract, and directly
serves the spec's SC-003 (recover from a stale cache) without requiring the user to remember to
run `reindex` manually after changing `EMBEDDING_MODEL`.

**Alternatives considered**: Leaving `compat.py` unwired until a later feature — rejected,
since shipping `ingest`/`sync` without this check would let them silently produce a Chroma store
mixing two incompatible embedding spaces, which is exactly the failure mode `compat.py` was
written to prevent.
