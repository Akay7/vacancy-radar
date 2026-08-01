# API Contract: `POST /similar`

## Request

Same convention as the existing `/analyze` stub (research.md's Endpoint signature decision):

```
POST /similar?jd_text=<pasted job description text>
```

`jd_text` is a required, non-empty (after stripping whitespace) string query parameter, per the
existing FastAPI scalar-parameter convention already established by the M1 scaffold.

## Response

`200 OK`, body: `list[SimilarVacancy]` (see data-model.md), ordered most-to-least similar,
already filtered to matches at or above `MIN_SIMILARITY` and truncated to `top_k`.

```json
[
  {
    "vacancy_id": "2026-01-15_acme-corp_backend-engineer",
    "company": "Acme Corp",
    "position": "Backend Engineer",
    "outcome": "applied",
    "similarity": 0.91,
    "excerpt": "We're looking for a Backend Engineer to build and scale our core API...",
    "is_duplicate": true
  }
]
```

An empty index or no matches above `MIN_SIMILARITY` returns `200 OK` with `[]` — never an error
(FR-006, SC-003).

## Error responses

- `422 Unprocessable Entity` — `jd_text` missing, empty, or whitespace-only (FR-005). This is
  FastAPI's standard validation response shape for a required parameter that fails validation;
  no custom error body is introduced.

## Cross-cutting

- Read-only: this endpoint never writes to the Chroma store, the manifest, or any vacancy
  folder.
- Depends on [[001-ingestion-cli]] having been run at least once; an empty/never-ingested index
  is a valid, supported state (User Story 3) — not an error.
