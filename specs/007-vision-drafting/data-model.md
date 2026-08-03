# Phase 1 Data Model: Vision-Based Image Drafting

## Persisted entities

**None new.** Per spec.md's Key Entities section, this feature changes *how*
`DraftVacancyMetadata` (introduced in [[006-vacancy-upload]]) is derived for image uploads —
its own shape, and the shape of the `VacancyRecord` eventually saved, are unchanged:

| Field | Type | Notes |
|---|---|---|
| `company` | `str` | Unchanged |
| `position` | `str` | Unchanged |
| `date` | `date` | Unchanged; still defaults to today when the model returns an empty string |

## Internal (non-persisted) request shape

`LLMProvider.draft_vacancy_metadata()` gains two optional parameters — not a new entity, just
an extended method contract shared by both providers (Constitution III):

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `document_text` | `str` | Yes (unchanged) | Extracted text for PDF/DOCX/plain-text uploads; always `""` for images now that local OCR is removed (FR-008) |
| `image_bytes` | `bytes \| None` | No, defaults to `None` | Raw image bytes, read from the staged upload file; `None` for non-image uploads |
| `image_media_type` | `str \| None` | No, defaults to `None` | `"image/png"` or `"image/jpeg"`, derived from the upload's file extension; `None` when `image_bytes` is `None` |

Both parameters are always passed together or not at all — there's no valid state with one
set and the other `None`, since a media type without bytes (or bytes without a media type) is
never constructed by the one caller (`api.py`'s `ingest_draft`). When `image_bytes` is set,
`document_text` carries no information (always `""`) — it exists only because it's part of the
one shared method signature both providers implement; the vision path does not read it.

## New mapping: `documents.IMAGE_MEDIA_TYPES`

| Extension | Media type |
|---|---|
| `.png` | `image/png` |
| `.jpg` | `image/jpeg` |
| `.jpeg` | `image/jpeg` |

Keys match the existing `documents.IMAGE_EXTENSIONS` set exactly — every extension already
routed to OCR extraction now also has a defined media type for the vision path.
