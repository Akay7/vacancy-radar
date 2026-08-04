# Data Model: Analyze and Log a Vacancy in One Pass

No new persisted entities. `Report`, `DraftVacancyMetadata`, and `VacancyRecord`
([[003-analyze-report-generation]], [[006-vacancy-upload]]) are unchanged in shape — this
feature is about how they get produced and displayed together, not new data.

## `_report.html`'s extended template context (not a Pydantic model)

| Key | Present when | Meaning |
|---|---|---|
| `report` | Always (paste or upload) | The existing `Report`, unchanged |
| `upload_token` | A file was uploaded | Same staging token `_ingest_draft.html`/`POST /ingest/confirm` already use — its presence is what triggers the "Log this vacancy" block |
| `original_filename` | A file was uploaded | Passed straight through to `_ingest_draft.html`, unchanged from its existing use |
| `draft` | A file was uploaded and drafting succeeded | The existing `DraftVacancyMetadata`, unchanged |
| `message` | A file was uploaded and either drafting or text-extraction failed | Existing failure-message convention from `_ingest_draft.html`, unchanged |

When no file is uploaded (paste-text path), `upload_token` is absent/`None` — `_report.html`
renders identically to its pre-existing behavior (FR-006), since the new block is conditional on
exactly that key.

## New provider method: `extract_document_text()` (not persisted — a request/response shape only)

```python
def extract_document_text(self, image_bytes: bytes, image_media_type: str) -> str:
    ...
```

Returns a plain-text transcription/summary of an image's job-posting content, used only as the
`jd_text`-equivalent input to `retriever.query_bullets()` / `query_similar_vacancies()` /
`run_analysis()` for image uploads specifically. Not returned to the client, not persisted —
purely an internal intermediate value for the duration of one request. Raises `LLMProviderError`
on failure (unreachable backend, no vision support), exactly like every other vision-path method.

## Route input shape: `POST /analyze` (extended)

| Field | Type | Required |
|---|---|---|
| `jd_text` | form text | One of `jd_text` / `file` must be given (mutually exclusive in intent — see contracts/analyze-upload-routes.md) |
| `file` | multipart file | One of `jd_text` / `file` must be given |

`POST /api/analyze`'s existing `jd_text`-only shape is unchanged (research.md #1).
