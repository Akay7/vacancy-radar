# Quickstart: Vacancy Document Upload

Validates the feature end-to-end. Unlike the automated suite (which fakes the LLM drafting
call), this exercises real text extraction — real PDF/DOCX parsing and real OCR — against a
real configured LLM backend, per this project's established pattern for anything a fake can't
meaningfully stand in for.

## Prerequisites

- API running with the updated `docker-compose.yml` (`./data/user` now read-write) or bare
  (`uvicorn vacancy_radar.api:app`) — either way, `VACANCY_DIR` must be writable by the process.
- `.env` has a working `LLM_PROVIDER` configured (Claude or Ollama).
- `tesseract-ocr` installed (already present in this dev environment — `tesseract --version`).
- A real posting/offer document in each format to test with: one PDF (with a text layer), one
  DOCX, one image (e.g., a screenshot of a job posting), and one plain-text file.

## Scenario 1 — Upload a PDF, draft, review, and confirm (User Story 1 / 2)

1. Open `http://localhost:8000/ingest`.
2. Upload a real job-posting PDF.

**Expected**: the review form appears with company/position/date pre-filled with values that
plausibly match the actual posting. Edit one field (e.g., correct the position title), type an
`outcome` (e.g. "applied"), and confirm.

**Expected**: a success message naming the new vacancy; check `VACANCY_DIR` on disk — a new
`YYYY-MM-DD_company-slug_position-slug/` folder exists, containing `vacancy.yaml` (with your
*edited* values, not the raw draft) and the original PDF under `sources/`.

## Scenario 2 — Image and DOCX uploads behave the same way (User Story 1)

Repeat Scenario 1 with the screenshot image and the DOCX file.

**Expected**: same drafting/review/confirm flow for both — the accepted format doesn't change
the UX. OCR quality on the image may be rougher than the PDF/DOCX text-layer extraction; this is
expected and exactly why every field stays editable before confirming.

## Scenario 3 — Immediately searchable (User Story 3)

Right after confirming Scenario 1's vacancy, submit a job posting with clearly similar wording to
`POST /similar`.

**Expected**: the just-created vacancy appears in the results — no `vacancy-radar ingest`/`sync`
was run separately.

## Scenario 4 — Natural-key conflict is surfaced, not silently lost (Edge Case / FR-006)

Upload and confirm the same document a second time with the same company/position/date.

**Expected**: the response clearly reports a conflict, naming both folders. Check `VACANCY_DIR`:
the second folder was still written to disk (nothing was lost), but `/similar` still only
reflects the first one until the conflict is resolved by hand (e.g., delete or rename one of the
two folders and re-run `vacancy-radar sync`).

## Scenario 5 — Draft failure still allows manual entry (Edge Case / FR-008)

Temporarily misconfigure the LLM backend (e.g., an invalid API key), then upload a document.

**Expected**: the review form still appears (fields blank, not pre-filled) with a clear message
that automatic drafting didn't work — you can still type every field manually and confirm
successfully. Restore the LLM configuration afterward.

## Scenario 6 — Unreadable document still allows manual entry (Edge Case)

Upload a corrupted or blank-page PDF (or an empty text file).

**Expected**: a clear message that the document's content couldn't be read, fields blank, still
confirmable by typing everything by hand.

## Scenario 7 — Unsupported file type is rejected clearly (Edge Case / FR-007)

Upload a file type outside image/PDF/DOCX/plain-text (e.g., a `.zip`).

**Expected**: a clear rejection message; nothing is staged, no form is rendered.

## Scenario 8 — Existing CLI ingestion accepts the same formats (User Story 4 / FR-009)

```bash
cp path/to/a-real-posting.pdf data/user/vacancies/<some-existing-folder>/sources/
vacancy-radar sync
```

**Expected**: the sync summary shows the folder as updated (not skipped, not erroring); a query
against `/similar`/`/analyze` reflects content from the newly-added PDF, the same way it already
does for a `.md` file in that folder.
