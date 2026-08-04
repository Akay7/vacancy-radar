# Quickstart: Analyze and Log a Vacancy in One Pass

Validates the feature end-to-end. The image-upload analysis path exercises real vision
extraction — like [[007-vision-drafting]], this needs a real configured backend to validate
meaningfully; the automated suite fakes the LLM.

## Prerequisites

- `vacancy-radar serve` running with a working `LLM_PROVIDER` configured.
- A real posting document in each format: PDF, DOCX, image (screenshot), plain text.

## Scenario 1 — Upload a PDF on the Analyze screen (User Story 1)

1. Open `http://localhost:8000/`.
2. Instead of pasting text, upload a real posting PDF.

**Expected**: a match report appears (score, flags, gaps, similar vacancies, draft paragraph),
comparable to what pasting that PDF's text would produce.

## Scenario 2 — Same, with an image (User Story 1)

Repeat Scenario 1 with a screenshot image instead of a PDF.

**Expected**: a match report still appears — produced via the new text-extraction-then-analyze
path (research.md #2), not a degraded or missing report.

## Scenario 3 — Report and draft together, then save (User Story 2)

1. Upload a posting document on the Analyze screen.
2. Alongside the match report, find the "Log this vacancy" section with company/position/date
   pre-filled.
3. Edit a field, type an outcome, and confirm.

**Expected**: a success message naming the new vacancy; check `VACANCY_DIR` — a new folder
exists with the *edited* values and the source document under `sources/`. No second upload or
screen visit was needed.

## Scenario 4 — Independent failure (User Story 2 / FR-007)

1. With a non-vision-capable Ollama model configured, upload an image on the Analyze screen.

**Expected**: the match report and/or the draft fields show their own specific failure message
(image-based analysis/drafting isn't available with the current setup) without blocking whatever
part *did* succeed independently.

## Scenario 5 — Pasting text is unchanged (User Story 3)

1. Paste job posting text (no file) on the Analyze screen.

**Expected**: only the match report appears — no draft fields, no save controls, identical to
pre-existing behavior.

## Scenario 6 — Startup fails fast without a configured API key

```bash
unset ANTHROPIC_API_KEY
LLM_PROVIDER=claude vacancy-radar serve
```

**Expected**: the process exits immediately with a message naming `ANTHROPIC_API_KEY` as missing
— the server never starts accepting requests. Confirm `LLM_PROVIDER=ollama vacancy-radar serve`
(no API key needed) starts normally.

## Automated coverage

`pytest` covers: `extract_document_text()` success/failure for both providers (faked HTTP/SDK
calls), `POST /analyze` with an uploaded file showing report+draft together and saving via the
existing `/ingest/confirm` route, the paste-only path staying byte-for-byte unchanged, and the
startup-validation `RuntimeError` via `with TestClient(app) as client:`.
