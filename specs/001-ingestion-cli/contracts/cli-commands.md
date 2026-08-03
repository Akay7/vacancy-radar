# CLI Command Contracts: Ingestion CLI

This feature is CLI-only (no HTTP endpoints change — `POST /ingest/vacancy` in `api.py` stays a
501 stub, out of scope per spec Assumptions). The contract surface is the three `vacancy-radar`
subcommands already declared in `cli.py`.

## `vacancy-radar ingest`

**Purpose**: First-time (or repeatable) full ingest of `CV_DIR` and `VACANCY_DIR` into Chroma.

**Args**: none beyond the global `CV_DIR`/`VACANCY_DIR`/`EMBEDDING_MODEL` environment variables
already defined in `.env.example`.

**Behavior**: functionally equivalent to `sync` run against an empty cache — same
new/changed-only logic (FR-004), it's just that on a fresh cache everything is "new." Exists as
a separate, memorable entry point for first-time setup (FR-001).

**Exit codes**: `0` on success, including a missing/empty `CV_DIR` or an empty `VACANCY_DIR`
(zero items found, FR-007). Non-zero when `VACANCY_DIR` does not exist at all — checked before
any of the three subcommands run, printing a clear stderr message rather than silently
reporting zero items (**amended** post-v0.1.0; see spec.md's FR-007) — or on another
unrecoverable error (e.g., `VACANCY_DIR` path exists but is not readable). Per-folder validation
failures (FR-008) and conflicts (FR-009) do NOT cause a non-zero exit, they're reported in the
summary.

**Stdout contract**: a human-readable run summary — counts for bullets ingested, vacancies
created, vacancies invalid (with folder + reason), vacancies conflicting (FR-006). Machine
consumption is not required for this feature (deferred; JSON output can be added later without
breaking this contract).

## `vacancy-radar sync`

**Purpose**: Incremental re-embed of only new/changed files since the last `ingest`/`sync`.

**Args**: same as `ingest`.

**Behavior**: consults `.cache/ingest-manifest.json` (see data-model.md) to skip unchanged
vacancy files (FR-004); always fully replaces `experience_bullets` (FR-012); never removes
entries for vacancy folders deleted/renamed on disk (FR-011) — see `reindex` for that.

**Exit codes**: same contract as `ingest`.

**Stdout contract**: same run-summary shape as `ingest`, plus a `vacancies_skipped` count
(unchanged folders) — see data-model.md's Run summary entity.

## `vacancy-radar reindex`

**Purpose**: Delete the entire local cache (`.cache/chroma/` + `.cache/ingest-manifest.json`)
and rebuild it from `CV_DIR`/`VACANCY_DIR` from scratch (FR-005).

**Args**: same as `ingest`.

**Behavior**: MUST NOT modify or delete anything under `CV_DIR`/`VACANCY_DIR` — only the local
cache directory. Also the path taken automatically by `ingest`/`sync` when
`compat.needs_reindex()` detects an embedding-model/schema mismatch (see research.md).

**Exit codes**: same contract as `ingest`.

**Stdout contract**: same run-summary shape as `ingest` (since post-reindex it's semantically a
from-scratch ingest).

## Cross-cutting

- All three commands read `CV_DIR`, `VACANCY_DIR`, `EMBEDDING_MODEL` from the environment
  (already defined in `.env.example`), consistent with how the FastAPI app is configured.
- All three commands are idempotent when re-run with no source changes (FR-010): a second
  `ingest` or `sync` produces the same summary shape with zero new/updated items.
