# Phase 1 Data Model: Ingestion CLI

## VacancyRecord

Parsed from a vacancy folder's `vacancy.yaml`. Source of truth lives in the user's own
`VACANCY_DIR`; this is a read/validate model, not a new persisted store.

| Field | Type | Required | Notes |
|---|---|---|---|
| `company` | str | yes | Used for the folder's natural key and as retrieval metadata |
| `position` | str | yes | Used for the folder's natural key and as retrieval metadata |
| `date` | date | yes | Used for the folder's natural key and as retrieval metadata |
| `outcome` | str | yes | Retrieval metadata (e.g., `applied`, `rejected`, `offer`) — free text, no enum enforced here |
| *(any other field)* | — | no | Passed through unvalidated (`extra="allow"`) — belongs to the maintainer's private schema, out of scope for this feature |

**Validation rules**:
- Missing any of `company`/`position`/`date`/`outcome` → folder is invalid (FR-008).
- `vacancy.yaml` absent or not parseable as YAML → folder is invalid (FR-008).

## Vacancy folder (natural key)

Not a separate persisted entity — the identity anchor for everything embedded from one folder.

- **Natural key format**: `YYYY-MM-DD_company-slug_position-slug` (folder name itself).
- **Validation**: must match `^\d{4}-\d{2}-\d{2}_[a-z0-9-]+_[a-z0-9-]+$`; failing folders are
  invalid (FR-008).
- **Conflict**: two folders whose *parsed* natural key (from `vacancy.yaml`, not just folder
  name) collide → both flagged as conflicting (FR-009).
- **Contents embedded**: `vacancy.yaml` (1 chunk, `doc_type=vacancy_meta`), each file under
  `sources/` (1 chunk each, `doc_type=posting`), each file under `correspondence/` (1 chunk
  each, `doc_type=correspondence`), `analysis.md` if present (1 chunk, `doc_type=analysis`).

## Chroma chunk (embedded document)

The unit stored in the `vacancies` or `experience_bullets` collection.

| Field | Type | Notes |
|---|---|---|
| `id` | str | `vacancies`: `<natural-key>/<relative-file-path>`; `experience_bullets`: not stable across runs (full-replace, no id reuse guarantee needed) |
| `document` | str | The chunk's text content |
| `metadata.doc_type` | str | One of `vacancy_meta`, `posting`, `correspondence`, `analysis` (vacancies only) |
| `metadata.company` | str | Copied from `VacancyRecord` (vacancies only) |
| `metadata.position` | str | Copied from `VacancyRecord` (vacancies only) |
| `metadata.date` | str (ISO) | Copied from `VacancyRecord` (vacancies only) |
| `metadata.outcome` | str | Copied from `VacancyRecord` (vacancies only) |

## IngestManifest

Local, disposable, regenerable — never committed, deleted by `reindex` along with the Chroma
store. Persisted as JSON at `.cache/ingest-manifest.json`.

| Field | Type | Notes |
|---|---|---|
| `compat_stamp` | `{embedding_model: str, schema_version: str}` | Mirrors `compat.CompatStamp`; compared against `compat.CURRENT_STAMP` on every run |
| `files` | map: relative path → `{content_hash: str, chunk_ids: list[str]}` | One entry per source file under `VACANCY_DIR` that has been ingested (vacancy folders only — CV bullets are full-replace and untracked here) |

**State transitions**:
- File new or `content_hash` changed → re-embed, upsert chunk(s), update entry.
- File unchanged → skip (sync's core optimization, FR-004).
- File's owning folder deleted from disk → entry remains stale until `reindex` (FR-011);
  `sync` does not consult the manifest to detect absence.
- `compat_stamp` mismatch → treat all files as needing re-embedding this run (full reindex),
  then rewrite `compat_stamp` to `CURRENT_STAMP`.

## Run summary (CLI output)

Not a persisted entity — the human-readable result of one `ingest`/`sync`/`reindex` invocation
(FR-006).

| Field | Type | Notes |
|---|---|---|
| `bullets_ingested` | int | Count written to `experience_bullets` this run |
| `vacancies_created` | int | New natural keys seen this run |
| `vacancies_updated` | int | Existing natural keys with at least one changed file this run |
| `vacancies_skipped` | int | Unchanged vacancy folders (sync only) |
| `vacancies_invalid` | list[{folder, reason}] | Folders failing validation (FR-008) |
| `vacancies_conflicting` | list[{natural_key, folders}] | Natural-key collisions (FR-009) |
