# Route Contract: `POST /analyze` (extended)

## Request (extended)

Multipart form, same as `POST /ingest/draft` already accepts:

| Field | Type | Notes |
|---|---|---|
| `jd_text` | text | Existing field, now optional |
| `file` | file | New — same accepted extensions as `POST /ingest/draft` (`.png`/`.jpg`/`.jpeg`, `.pdf`, `.docx`, `.txt`/`.md`) |

Exactly one of `jd_text` (non-blank) / `file` is expected to be meaningfully present. If both are
given, `file` takes precedence (a file is a stronger signal of intent than leftover text in the
box). If neither is given, the route renders `_error.html` with the existing "paste a job
posting" validation message — unchanged from today.

## Response — unchanged for the paste-text case

When `file` is absent, the response is `_report.html` rendered exactly as today (FR-006) —
`upload_token` is not passed into the context, so the new "Log this vacancy" block never renders.

## Response — new, when `file` is present

1. `_stage_and_read_upload(file)` (extracted from `ingest_draft()`) stages the file and returns
   its `(token, document_text, image_bytes, image_media_type)` — an unsupported extension
   short-circuits straight to `_error.html`, identical to `POST /ingest/draft`'s existing
   behavior.
2. **Drafting** (independent of analysis — FR-007): calls `draft_vacancy_metadata(document_text,
   image_bytes=, image_media_type=)`, unchanged from `POST /ingest/draft`. Success → `draft`;
   failure → `message` (same wording rules as today's route: image-specific vs. generic).
3. **Query text for analysis**: non-image → `document_text` directly; image → calls
   `extract_document_text(image_bytes, image_media_type)` (contracts/llm-provider-extract-text.md).
   A failure here produces its own report-side failure message (FR-007) — independent of step 2's
   outcome.
4. **Analysis** (only if step 3 produced text): calls the existing `run_analysis(query_text,
   retriever, llm_provider)` — byte-for-byte the same function the paste-text path and
   `POST /api/analyze` already call.
5. **Render**: `_report.html` with the analysis result (or its failure message) *and*
   `upload_token`/`original_filename`/`draft`/`message` from steps 1–2 — triggering the
   "Log this vacancy" include (data-model.md).

## Save step — reused, not reimplemented

The "Log this vacancy" block is `_ingest_draft.html`, posting to the existing
`POST /ingest/confirm` — unchanged in every respect (same required fields, same conflict
handling, same immediate embed-on-save). FR-008 is satisfied by reuse, not by re-implementing
equivalent behavior.

## Non-goals

- `POST /api/analyze` (JSON) is unchanged — no `file` field, no new behavior (research.md #1).
- No new "confirm" route or variant — `POST /ingest/confirm` is called exactly as it is today,
  regardless of whether the upload token came from `/ingest/draft` or this route.
