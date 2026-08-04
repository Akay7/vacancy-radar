# Data Model: Clear Navigation & Visual Polish for Ingest Flow

No new persisted or cached entities — this feature is presentation, navigation, and routing
only. The data already modeled in [[006-vacancy-upload]] (`DraftVacancyMetadata`,
`VacancyRecord`) and [[003-analyze-report-generation]] (`Report`) is unchanged in shape.

## `IngestStep` (new — presentation-only concept, not a Pydantic model, not persisted)

The three states the log-a-vacancy screen can be in. Not a new state-tracking mechanism (see
research.md #3) — each value corresponds 1:1 with a partial template that a route already
returns today; this feature just names the value and passes it into that partial's existing
template context so shared step-indicator markup can render against it.

| Step | Rendered by | Route that returns it | Meaning |
|---|---|---|---|
| `upload` | `ingest.html` | `GET /ingest` | Waiting for a file to be selected/submitted |
| `review` | `_ingest_draft.html` | `POST /ingest/draft` | Draft fields shown, editable, not yet saved (or drafting failed — see `error` below) |
| `done` | `_ingest_result.html` (`success=True`) | `POST /ingest/confirm` | Vacancy folder written and embedded |
| `error` | `_ingest_draft.html` (no draft) or `_ingest_result.html` (`success=False`) | `POST /ingest/draft` or `POST /ingest/confirm` | The current step's action failed; the message explains why and what the user can still do |

`error` is not a distinct route — it's a rendering of the same partial as `review`/`done` with
`message` set and `draft`/`success` reflecting the failure, exactly as today; this feature only
adds the `step` context value and the associated CSS treatment (FR-005) on top of that existing
behavior.

## Route shape (renamed, not restructured — see contracts/route-restructure.md)

`Report`, `SimilarVacancy`, `DraftVacancyMetadata`, and `VacancyRecord` request/response bodies
are all byte-for-byte unchanged. Only the URL paths they're served from move, per
contracts/route-restructure.md.
