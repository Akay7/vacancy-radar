# Route Contracts: Vacancy Document Upload

Three routes on the existing FastAPI app. This is the first real "log a vacancy" implementation
— the M1-scaffold's `POST /ingest/vacancy` stub (a bare `vacancy_folder: str` path parameter, for
a different, never-built idea) never returned anything but `501`, so nothing could depend on
real behavior from it. **Corrected during implementation**: rather than redefining that same
path, this feature retires it entirely (removed from `api.py`) in favor of `GET /ingest` +
`POST /ui/ingest/draft` + `POST /ui/ingest/confirm`, matching the `/ui/analyze` naming
convention [[005-minimal-ui]] already established for HTML-rendering routes sitting alongside
their JSON counterparts.

## `GET /ingest`

**Purpose**: Serve the upload screen — a single file input (image, PDF, DOCX, or plain text)
and a submit control.

**Response**: `200 OK`, `text/html` — renders the upload form. No draft is present on first
load.

## `POST /ui/ingest/draft`

**Purpose**: Accept the uploaded document, extract its text locally, ask the configured
`LLMProvider` to draft company/position/date, and render an editable review form.

**Request**: `multipart/form-data`, one field: the uploaded file.

**Response**: Always `200 OK`, `text/html`:
- On successful extraction + drafting: a form pre-filled with the drafted company/position/date
  (all editable) and an empty, required outcome field, plus a hidden `upload_token` field
  (research.md #4) and a "Confirm & Save" control.
- On unreadable/empty extraction, or an unavailable/failed LLM backend (FR-008): the same form,
  fields blank instead of pre-filled, with a clear message explaining that automatic drafting
  didn't work and the maintainer can fill in every field manually — the upload itself is still
  staged (research.md #4), so the maintainer doesn't need to re-upload.
- On an unsupported file type or a request with no file at all (FR-007): an error message, no
  form rendered, nothing staged.

## `POST /ui/ingest/confirm`

**Purpose**: Take the (possibly edited) company/position/date/outcome fields plus the
`upload_token`, write a real vacancy folder into `VACANCY_DIR`, and immediately ingest it.

**Request**: `application/x-www-form-urlencoded` fields: `company`, `position`, `date`,
`outcome`, `upload_token`.

**Response**: Always `200 OK`, `text/html`:
- **Success**: no folder already exists at the computed natural key's path — the folder is
  written, the staged upload is moved into its `sources/`, `ingest.ingest_vacancies()` is
  re-invoked over `VACANCY_DIR`, and its `RunSummary.vacancies_created == 1` confirms the
  upsert. A success message names the new vacancy.
- **Same-key conflict** (FR-006 — **corrected during implementation**, see below): a folder
  already exists at exactly the natural key's path. Nothing is written or moved — the existing
  folder is left completely untouched, and the response explains a vacancy already exists at
  that date/company/position, inviting the maintainer to edit a field (a different date, a
  corrected company name) or resolve the existing folder by hand. The staged upload is *not*
  consumed, so the same `upload_token` can be resubmitted with corrected fields without
  re-uploading the document.
- **Invalid/missing `upload_token`** (e.g., the staged file was already consumed, or the token
  is stale/unknown): a clear error, nothing written.

**Correction from the original design**: this route uses the natural key directly as the new
folder's name (`VACANCY_DIR/<natural-key>/`), unlike [[001-ingestion-cli]]'s conflict scenario
(two *differently-named* folders whose `vacancy.yaml` content happens to resolve to the same
key). Writing into an already-existing same-named folder would silently overwrite/merge with
whatever vacancy is already there — a real data-loss risk — so this route checks for that
*before* writing anything, rather than writing first and relying on `ingest_vacancies()`'s
cross-folder conflict detection to catch it afterward (by then the original folder's content
would already be gone). `ingest_vacancies()`'s own conflict detection (reused unchanged) still
runs afterward and remains the safety net for the different scenario it was built for — a
separately-named folder whose content collides with the new one.

## Cross-cutting

- Neither route calls `LLMProvider` for anything except the one `draft_vacancy_metadata()` call
  in `POST /ui/ingest/draft` — `POST /ui/ingest/confirm` never touches the LLM at all.
- `POST /ui/ingest/confirm` never re-derives fields from the document itself; it only ever
  writes back the values that came from the submitted form, whatever the maintainer left them
  as after review (FR-004).
- Both routes reuse `ingest.natural_key()`/`slugify()`/`ingest_vacancies()` unchanged — no
  parallel natural-key or conflict-detection logic exists anywhere in this feature.
- Existing folder-based ingestion (`vacancy-radar ingest`/`sync`/`reindex`) gains the same
  extraction capability for `sources/`/`correspondence/` files (FR-009) via the same
  `documents.extract_text()` function these routes use — one shared implementation, not two.
