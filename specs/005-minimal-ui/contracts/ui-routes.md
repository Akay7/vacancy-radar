# Route Contracts: Minimal UI

Two new routes on the existing FastAPI app, plus one additive field on the existing
`POST /analyze` JSON contract. `POST /similar`, `GET /healthz`, and `POST /ingest/vacancy` are
unchanged (see [[002-similar-retrieval]], [[001-ingestion-cli]]).

## `GET /`

**Purpose**: Serve the page shell — the paste-JD form.

**Response**: `200 OK`, `text/html` — renders `templates/index.html`. No report is present on
first load; the result area starts empty until a submission comes back.

## `POST /ui/analyze`

**Purpose**: The HTML counterpart to `POST /analyze` — same analysis, rendered as HTML instead
of JSON, submitted by the page's form (via HTMX, `hx-post="/ui/analyze"`, swapping the response
into the result container).

**Request**: `application/x-www-form-urlencoded`, one field: `jd_text`.

**Response**: Always `200 OK`, `text/html` — one of three rendered partials:
- `_report.html` — the full match report, including `draft_sentences` rendered with each
  sentence's citation shown inline (FR-003), similar vacancies with outcome/duplicate status
  (FR-004), and the "nothing to show yet" fallback when the report is empty (FR-009).
- `_error.html`, validation message — when `jd_text` is empty/whitespace-only; no call into
  `run_analysis()` is made (FR-008).
- `_error.html`, backend-failure message — when `run_analysis()` raises the same
  `LLMProviderError`/`ValidationError`/`json.JSONDecodeError` the JSON route turns into a `502`;
  here it's a plain-language message instead (FR-007).

**Why always `200`**: see research.md #5 — this route's only consumer is the browser rendering
HTML, so the distinction between "invalid input" and "backend failure" is carried in which
partial (and which message) is rendered, not in the HTTP status code.

## `POST /analyze` (existing — additive change only)

**Change**: The JSON response gains one field, `draft_sentences: list[{text: str, citation:
{quote: str, source_id: str}}]`, per data-model.md. `draft_paragraph`, `citations`, `flags`,
`gaps`, `similar`, and `score` are all unchanged in shape and content. Status codes (`200`,
`422` on empty `jd_text`, `502` on backend failure) are unchanged.

**Backward compatibility**: Existing consumers of this endpoint (including
[[003-analyze-report-generation]]'s own test suite) continue to work unmodified — they simply
don't read the new field.

## Cross-cutting

- Both `GET /` and `POST /ui/analyze` call the same `run_analysis(jd_text, retriever,
  llm_provider) -> Report` function `POST /analyze` calls (research.md #3) — there is exactly
  one place the retrieval → prompt → LLM → grounding pipeline is implemented, regardless of
  which route triggered it.
- Neither new route calls an `LLMProvider` directly, and neither introduces a new provider
  branch — `get_llm_provider()`'s existing `LLM_PROVIDER` env-driven resolution
  ([[003-analyze-report-generation]]) is reused unchanged (Constitution III).
- The vendored `src/vacancy_radar/static/htmx.min.js` (URL path `/static/htmx.min.js`) is served
  via FastAPI's existing static-file mounting (no new dependency —
  `starlette.staticfiles.StaticFiles`, already part of FastAPI's own dependency tree).
