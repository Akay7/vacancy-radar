# Quickstart: Minimal UI

Validates the feature end-to-end in a browser. Unlike `/analyze`'s own quickstart
([[003-analyze-report-generation]]), this one is about the presentation layer — it assumes
`/analyze` itself already works and focuses on what's new: the page, the form, and the
rendered report.

## Prerequisites

- `data/example/` ingested: `vacancy-radar ingest`
- API running: `uvicorn vacancy_radar.api:app` (bare) or `docker compose up`
- `.env` has a working `LLM_PROVIDER` configured (Claude or Ollama), same as
  [[003-analyze-report-generation]]'s quickstart

## Scenario 1 — Paste a posting, see the full report (User Story 1)

Open `http://localhost:8000/` in a browser, paste the contents of
`data/example/vacancies/2026-01-15_acme-corp_backend-engineer/sources/posting.md` into the
textarea, and submit.

**Expected**: without a full page reload, the result area fills in with: the match band, at
least one green flag whose reason references real ingested experience, any gaps, and (if the
posting is similar to ingested history) at least one similar vacancy with its outcome.

## Scenario 2 — Draft paragraph with inline citations (User Story 2)

Same submission as Scenario 1. **Expected**: the draft opening paragraph is rendered as a
sequence of sentences, each one visibly paired with the citation that grounds it — not a flat
paragraph with citations listed separately with no link back to which sentence they support.

## Scenario 3 — Copy the draft paragraph (User Story 2)

From the rendered report in Scenario 1/2, trigger the copy action next to the draft paragraph.

**Expected**: the clipboard contains exactly the draft paragraph's text (verify by pasting it
into another application) — not the surrounding HTML, not the citations.

## Scenario 4 — Empty input is rejected before any request (User Story 3 / FR-008)

With the textarea empty (or whitespace-only), attempt to submit.

**Expected**: a clear "paste a job posting" message appears; confirm via browser dev tools that
no `POST /ui/analyze` request was actually sent.

## Scenario 5 — Backend/LLM unavailable (User Story 3 / FR-007)

Temporarily set an invalid `ANTHROPIC_API_KEY` (or stop the local Ollama server if using that
profile), restart the server, and submit a valid posting.

**Expected**: a plain-language message explaining the analysis backend is unavailable — not a
blank result area, not a raw stack trace, and the browser's network tab shows `200 OK` for
`POST /ui/analyze` (per research.md #5 — the failure is carried in the rendered content, not
the HTTP status).

## Scenario 6 — Cold start: nothing ingested yet (FR-009)

```bash
rm -rf .cache
```

Submit any posting text.

**Expected**: the result area clearly states nothing could be matched yet (empty flags, empty
citations, empty draft paragraph) — not blank-looking sections that read as broken. Re-run
`vacancy-radar ingest` afterward to restore the index.

## Scenario 7 — Loading state and duplicate-submission guard (Edge case)

Submit a posting against a real (non-instant) LLM backend and, while the request is in flight,
attempt to submit again immediately.

**Expected**: a visible loading indicator appears immediately on the first submission; the
submit control is disabled until the first response returns, so a second identical request
cannot be triggered by an impatient double-click.

## Scenario 8 — `POST /analyze` JSON contract is unaffected (Backward compatibility)

```bash
curl -s -G -X POST "http://localhost:8000/analyze" --data-urlencode "jd_text=$(cat data/example/vacancies/2026-01-15_acme-corp_backend-engineer/sources/posting.md)" | python3 -m json.tool
```

**Expected**: the response contains every field it did before
([[003-analyze-report-generation]]'s quickstart Scenarios 1-7 still pass unmodified), plus the
new `draft_sentences` array — existing consumers reading only the old fields are unaffected.
