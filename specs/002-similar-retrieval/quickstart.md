# Quickstart: `/similar` Retrieval

Validates the feature end-to-end using the sanitized `data/example/` fixture set populated by
[[001-ingestion-cli]] (never real personal data — Constitution I).

## Prerequisites

- `data/example/` ingested at least once: `vacancy-radar ingest` (see
  [001-ingestion-cli/quickstart.md](../001-ingestion-cli/quickstart.md))
- API running: `uvicorn vacancy_radar.api:app` (bare) or `docker compose up`

## Scenario 1 — Near-duplicate match with outcome (User Story 1)

```bash
curl -X POST "http://localhost:8000/similar" --data-urlencode "jd_text=$(cat data/example/vacancies/2026-01-15_acme-corp_backend-engineer/sources/posting.md)"
```

**Expected**: `200 OK`; first result's `vacancy_id` is
`2026-01-15_acme-corp_backend-engineer`, `outcome` is `applied`, `similarity` is high
(near 1.0, since the text is identical to what was ingested).

## Scenario 2 — Unrelated JD text (User Story 1 / SC-002)

```bash
curl -X POST "http://localhost:8000/similar" --data-urlencode "jd_text=Seeking an experienced pastry chef for a Michelin-starred restaurant."
```

**Expected**: `200 OK`; `[]` or only genuinely unrelated-but-above-threshold noise is absent —
no fixture vacancy should appear as a "similar" match to a pastry chef posting.

## Scenario 3 — Duplicate-application flag (User Story 2)

```bash
curl -X POST "http://localhost:8000/similar" --data-urlencode "jd_text=Acme Corp is hiring a Backend Engineer to build and scale our core API using FastAPI and PostgreSQL."
```

**Expected**: the Acme Corp match has `"is_duplicate": true`.

## Scenario 4 — Same company, different role (User Story 2, negative case)

```bash
curl -X POST "http://localhost:8000/similar" --data-urlencode "jd_text=Acme Corp is hiring a Senior Product Designer to lead our design system."
```

**Expected**: if Acme Corp's Backend Engineer posting appears at all, it does NOT have
`"is_duplicate": true` (different role, similarity below `DUPLICATE_SIMILARITY`).

## Scenario 5 — Empty index (User Story 3 / cold start)

```bash
rm -rf .cache/chroma .cache/ingest-manifest.json
curl -X POST "http://localhost:8000/similar" --data-urlencode "jd_text=Any job description text."
```

**Expected**: `200 OK`; `[]` — not an error.

## Scenario 6 — Empty JD text rejected (FR-005)

```bash
curl -X POST "http://localhost:8000/similar" --data-urlencode "jd_text= "
```

**Expected**: `422 Unprocessable Entity`, not a 200 with an empty or nonsensical result.
