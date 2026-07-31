# Quickstart: Ingestion CLI

Validates the feature end-to-end using the sanitized `data/example/` fixture set (never real
personal data — Constitution I).

## Prerequisites

- `pip install -e .[dev]` (or `docker compose build`)
- `.env` present (copy from `.env.example`); `CV_DIR=./data/example`,
  `VACANCY_DIR=./data/example/vacancies` for this validation run
- `data/example/` populated with at least: one CV bullets markdown file, and 2-3 vacancy
  folders (including at least one with a non-conforming folder name and one with a missing
  required `vacancy.yaml` field, to exercise FR-008)

## Scenario 1 — First ingest (User Story 1)

```bash
rm -rf .cache/chroma .cache/ingest-manifest.json   # start from a clean cache
vacancy-radar ingest
```

**Expected**: exit code `0`; summary reports non-zero `bullets_ingested` and
`vacancies_created` matching the example fixture count; any intentionally malformed fixture
folder appears under `vacancies_invalid` with a clear reason, not a crash.

## Scenario 2 — Incremental sync (User Story 2)

```bash
# add a new vacancy folder under data/example/vacancies/, or edit one vacancy.yaml's `outcome`
vacancy-radar sync
```

**Expected**: summary reports the new/edited folder under `vacancies_created`/`vacancies_updated`
respectively; all other previously-ingested vacancy folders appear under `vacancies_skipped`,
not re-embedded. Editing CV bullets and re-running `sync` fully replaces
`experience_bullets` (no duplicates, no stale bullets).

## Scenario 3 — Full reindex (User Story 3)

```bash
rm -rf .cache/chroma .cache/ingest-manifest.json   # simulate a corrupted cache
vacancy-radar reindex
```

**Expected**: resulting collections match Scenario 1's counts exactly; `data/example/` files
are untouched (verify with `git status` — no diffs, since it's git-tracked fixture data).

## Scenario 4 — Idempotency check (FR-010)

```bash
vacancy-radar ingest
vacancy-radar ingest
```

**Expected**: both runs report identical counts; the second run's summary shows the same
`vacancies_created` count as the first (not doubled) — confirms upsert-by-natural-key, not
duplicate insertion.

## Scenario 5 — Compat-stamp auto-reindex (research.md decision)

```bash
vacancy-radar ingest
# then change EMBEDDING_MODEL in .env to a different model name
vacancy-radar sync
```

**Expected**: `sync` detects the stamp mismatch and performs a full reindex automatically
(summary counts match a fresh `ingest`, not an incremental no-op), then subsequent `sync` runs
go back to incremental behavior.
