# Feature Specification: Ingestion CLI

**Feature Branch**: `001-ingestion-cli`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "Ingestion CLI — experience bullets + vacancy folders → Chroma, upsert-keyed by natural key" (first unchecked item on the README roadmap)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - First-time ingest populates the local index (Priority: P1)

As the user, the first time I run the ingest command against my CV bullets and vacancy
folders, my local vector store is populated so that `/analyze` and `/similar` (once built)
have something to retrieve against.

**Why this priority**: Nothing else in the roadmap (`/similar`, `/analyze`, eval harness) can
be built or tested without a populated index. This is the on-ramp for every other feature.

**Independent Test**: Point `CV_DIR`/`VACANCY_DIR` at `data/example/`, run the ingest command
once, and confirm both collections (experience bullets, vacancies) contain entries matching the
example data, each tagged with its retrieval metadata.

**Acceptance Scenarios**:

1. **Given** an empty local cache and a `CV_DIR` containing CV bullet markdown, **When** the
   user runs the ingest command, **Then** every bullet is embedded into the experience-bullets
   collection.
2. **Given** an empty local cache and a `VACANCY_DIR` containing one or more vacancy folders,
   **When** the user runs the ingest command, **Then** each vacancy folder's content is embedded
   into the vacancies collection, tagged with company/position/date/outcome metadata, keyed by
   the folder's natural key.
3. **Given** a fresh clone with no prior cache, **When** the user runs the ingest command,
   **Then** the command reports a summary count of bullets and vacancies ingested and exits
   successfully.

---

### User Story 2 - Incremental sync after adding or editing a vacancy (Priority: P2)

As the user, after I apply to a new posting or update an existing vacancy's outcome, I run a
sync command so only what changed gets re-embedded — not the entire history.

**Why this priority**: Vacancy folders accumulate over an entire job search; re-embedding
everything on every edit would make the tool slower and more expensive to use with every
posting added, discouraging regular use.

**Independent Test**: Ingest `data/example/` once, add one new vacancy folder and edit one
existing `vacancy.yaml` outcome field, run the sync command, and confirm only the new and
edited entries were re-embedded (verified via the per-file hash cache / a before-and-after
count of embedding calls).

**Acceptance Scenarios**:

1. **Given** a previously ingested vacancy folder with no changes, **When** the user runs the
   sync command, **Then** that folder's files are not re-embedded.
2. **Given** a new vacancy folder added since the last ingest/sync, **When** the user runs the
   sync command, **Then** the new folder's content is embedded and tagged like any other
   vacancy.
3. **Given** an existing vacancy folder where only `vacancy.yaml`'s outcome changed, **When**
   the user runs the sync command, **Then** only that file's embedded chunk(s) are updated,
   leaving unrelated files (e.g., posting snapshots) untouched.
4. **Given** new CV bullets added to `CV_DIR` since the last run, **When** the user runs the
   sync command, **Then** the entire experience-bullets collection is replaced from the current
   contents of `CV_DIR`, so the new bullets appear and no stale or duplicate bullets remain.
5. **Given** a vacancy folder deleted from `VACANCY_DIR` since the last run, **When** the user
   runs the sync command, **Then** the corresponding vacancy entry remains in the local cache
   (sync does not reconcile deletions; see reindex, User Story 3).

---

### User Story 3 - Full rebuild from source (Priority: P3)

As the user, if I suspect my local cache is stale, corrupted, or I've changed the embedding
model, I run a reindex command to wipe the local cache and rebuild it entirely from my
git-tracked source data, without touching that source data.

**Why this priority**: Recovery path, not a per-session need — but essential because the cache
is explicitly designed to be disposable (per project [[constitution|constitution]] Principle
VI); the CLI must make good on that promise with a real, working command.

**Independent Test**: Ingest `data/example/`, delete or corrupt the local cache directory
directly, run the reindex command, and confirm the resulting index matches what a first-time
ingest against the same source data would produce.

**Acceptance Scenarios**:

1. **Given** a populated local cache, **When** the user runs the reindex command, **Then** the
   existing cache is deleted and rebuilt from `CV_DIR` and `VACANCY_DIR` from scratch.
2. **Given** source data unchanged since the last ingest, **When** the user runs reindex instead
   of sync, **Then** the resulting collections are equivalent in content to before the reindex
   (same bullets, same vacancies, same metadata).
3. **Given** a reindex in progress, **When** the command completes, **Then** none of the
   git-tracked source files (CV bullets, vacancy folders) have been modified or deleted.

---

### Edge Cases

- What happens when `CV_DIR` is empty or does not exist yet? The command should complete
  without error, reporting zero bullets ingested, not fail — a CV isn't required to start
  logging vacancy history.
- What happens when `VACANCY_DIR` does not exist at all? **Amended** (post-v0.1.0, per
  maintainer decision): this is now a hard error (non-zero exit, clear stderr message) rather
  than a silent zero-item state — unlike a missing CV, there is nothing useful this tool can do
  without vacancy history, and a missing directory is far more likely to mean a misconfigured
  `VACANCY_DIR` than a deliberately-empty one. An `VACANCY_DIR` that exists but is genuinely
  empty (no vacancy folders yet) is still a valid zero-item state, not an error.
- How does the system handle a vacancy folder whose name doesn't follow the
  `YYYY-MM-DD_company-slug_position-slug` natural-key convention? It should be reported as a
  skipped/invalid folder with a clear reason, without stopping ingestion of the remaining
  folders.
- How does the system handle a vacancy folder missing required `vacancy.yaml` fields (company,
  position, date, outcome)? It should be reported as a skipped/invalid folder with a clear
  reason, without stopping ingestion of the remaining folders.
- How does the system handle two vacancy folders that resolve to the same natural key (e.g.,
  duplicated by accident)? It should be reported as a conflict and both flagged, rather than
  silently overwriting one with the other.
- What happens when a previously ingested vacancy folder is deleted or renamed on disk? `sync`
  leaves its Chroma entry in place (stale); only running `reindex` clears it, since `sync` only
  detects new/changed files (FR-011).
- What happens if the ingest/sync command is interrupted partway through (e.g., killed
  mid-run)? Re-running it afterward should converge to a correct state rather than leaving
  duplicate or partial entries.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The CLI MUST provide an ingest command that reads CV bullet markdown from
  `CV_DIR` and vacancy folders from `VACANCY_DIR`, embedding them into two separate collections:
  experience bullets and vacancies.
- **FR-002**: The system MUST derive each vacancy's identity from its folder's natural key
  (date + company slug + position slug) rather than a content hash, so re-running ingestion
  updates the same entry instead of creating duplicates.
- **FR-003**: The system MUST tag every embedded vacancy-folder chunk with retrieval metadata:
  doc type, company, position, date, and outcome.
- **FR-004**: The CLI MUST provide a sync command that re-embeds only files that changed since
  the last ingest/sync (via a per-file staleness check), leaving unchanged entries untouched.
  Deleted or renamed vacancy folders are explicitly out of scope for sync (see FR-011).
- **FR-005**: The CLI MUST provide a reindex command that deletes the entire local cache and
  rebuilds it from source data, without modifying or deleting any source files.
- **FR-006**: Each of the ingest, sync, and reindex commands MUST report a summary of items
  processed (created, updated, skipped, invalid) when it completes.
- **FR-007**: The system MUST treat an empty `CV_DIR`/`VACANCY_DIR`, or a missing `CV_DIR`, as
  a valid zero-item state, not an error. **Amended** (post-v0.1.0): a missing `VACANCY_DIR`
  (the directory does not exist at all) is a hard error instead — see the Edge Cases entry
  above for the reasoning.
- **FR-008**: The system MUST detect a vacancy folder that is missing required `vacancy.yaml`
  fields or does not follow the natural-key naming convention, report it as invalid with a
  clear reason, and continue processing the remaining folders rather than aborting the run.
- **FR-009**: The system MUST detect two vacancy folders that resolve to the same natural key
  and report the conflict rather than silently overwriting one entry with the other.
- **FR-010**: Running the ingest command a second time with no source changes MUST be
  idempotent: it MUST NOT create duplicate entries or re-embed unchanged content.
- **FR-011**: The sync command MUST NOT detect or clean up entries for vacancy folders deleted
  or renamed since the last run — reconciling deletions/renames is deferred entirely to the
  reindex command (FR-005). `sync` only detects new and changed files.
- **FR-012**: CV bullets MUST be upserted via a full replace of the experience-bullets
  collection on every ingest/sync run (no per-bullet stable identity or incremental staleness
  tracking), since `CV_DIR` is expected to be small and change infrequently.

### Key Entities *(include if feature involves data)*

- **CV bullet**: A single markdown bullet point describing a piece of the user's real
  experience; the unit embedded into the experience-bullets collection and later cited by
  `/analyze` as grounding for generated claims.
- **Vacancy folder**: One job posting the user has engaged with, identified by a natural key
  (`YYYY-MM-DD_company-slug_position-slug`); contains a source-of-truth `vacancy.yaml`
  (company, position, date, outcome, and related metadata) plus supporting artifacts —
  posting snapshots, correspondence, and generated analysis — each embedded and tagged with
  metadata derived from `vacancy.yaml`.
- **Local cache (Chroma collections)**: Regenerable derived state — `experience_bullets` and
  `vacancies` — built entirely from CV bullets and vacancy folders; never the source of truth,
  never committed to git.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with an existing `data/user/` of CV bullets and vacancy folders can
  populate their local index from a fresh clone with a single command.
- **SC-002**: After the initial ingest, adding one new vacancy or editing one existing
  vacancy's outcome and re-running sync only touches the changed entry — unchanged vacancies
  and bullets are left untouched, so day-to-day use scales with the number of new/changed
  postings, not with total job-search history size.
- **SC-003**: A user can recover from a corrupted or stale local cache and be back to a fully
  populated, correct index using a single recovery command, with zero risk to their underlying
  CV/vacancy source data.
- **SC-004**: Malformed or misnamed vacancy folders are surfaced to the user in plain language
  (which folder, what's wrong) rather than as a crash, and do not block ingestion of the rest
  of the user's data.
- **SC-005**: Re-running the same ingest or sync command twice in a row with no source changes
  produces an identical index both times (no duplicate or drifting entries).

## Assumptions

- `vacancy.yaml` MUST at minimum carry the four fields already required for retrieval tagging —
  company, position, date, outcome — per `retriever.py`'s existing metadata contract; folders
  missing any of these are treated as invalid per FR-008. The full private schema (additional
  optional fields) is out of scope for this spec.
- The natural-key folder naming convention is `YYYY-MM-DD_company-slug_position-slug`, per the
  README's documented data model.
- Two Chroma collections are used, matching the existing `retriever.py`/README naming:
  `experience_bullets` and `vacancies`.
- The local cache lives at `.cache/chroma` (or wherever `Retriever`/embedding config already
  point), consistent with the existing scaffold.
- This feature covers the `ingest`, `sync`, and `reindex` CLI subcommands already stubbed in
  `cli.py`; performance targets (e.g., embedding throughput) are out of scope and deferred to
  the eval harness roadmap item.
- `import-fods` (one-time `Job.fods` spreadsheet → vacancy folders conversion, also stubbed in
  `cli.py`) is explicitly out of scope for this spec and tracked as a separate future feature.
- Concurrent runs of ingest/sync/reindex against the same cache from multiple processes are out
  of scope (single-user, single-process CLI tool).
