# Quickstart: Clear Navigation & Visual Polish for Ingest Flow

Validates the feature end-to-end in a browser, plus the restructured JSON API paths via `curl`.

## Prerequisites

- `vacancy-radar serve` running (bare, `--host 127.0.0.1` default) or the full docker-compose
  stack.
- A working `LLM_PROVIDER` configured (Claude or Ollama) for the ingest-draft scenario; the
  navigation/styling scenarios don't require a live LLM backend.

## Scenario 1 — Discover the ingest flow from the home screen (User Story 1)

1. Open `http://localhost:8000/`.
2. Without typing any other URL, find and click the link to log a vacancy.

**Expected**: a visible "Log a vacancy" link is present without scrolling past unrelated
content; clicking it navigates to `/ingest`. On `/ingest`, an equally visible link back to
Analyze is present (contracts/nav-and-step-ui.md).

## Scenario 2 — Step visibility through the ingest flow (User Story 2)

1. On `/ingest`, upload a real posting/offer file.
2. Observe the screen while the draft is being generated, then once it completes.
3. Fill in/edit the fields, type an outcome, and confirm.

**Expected**: a distinct in-progress indication appears during drafting (not just an unchanged
form); the review step is visually marked as step "review" once the draft appears
(`data-step="review"`); after confirming, the screen is visually marked as step "done"
(`data-step="done"`) with a success message.

## Scenario 3 — Error is visually distinct (User Story 2)

1. On `/ingest`, upload a file type the configured backend can't draft from (e.g. an image
   against a non-vision-capable Ollama model), or an unsupported extension.

**Expected**: the message renders with the `.error` / `data-step="error"` treatment (color/icon),
clearly different from the normal review/done styling, and states that manual entry is still
available.

## Scenario 4 — Shared visual identity (User Story 3)

1. Open `/` and `/ingest` side by side (two tabs).

**Expected**: same typography, spacing, button style, and nav placement on both — no visible
seam suggesting they're different apps.

## Scenario 5 — Restructured JSON API paths

```bash
curl -s -X POST "http://localhost:8000/api/analyze?jd_text=Senior+Python+Engineer..." | jq .score
curl -s -X POST "http://localhost:8000/api/similar?jd_text=Senior+Python+Engineer..." | jq .
```

**Expected**: both succeed exactly as the old `/analyze`/`/similar` paths did; the old paths
(`POST /analyze` JSON semantics, `POST /similar`) now 404, since `/analyze` is reassigned to the
HTML route (contracts/route-restructure.md).

## Scenario 6 — Nav visible at mobile width (FR-008)

1. Resize the browser (or use dev tools' device toolbar) to 375px wide on `/` and `/ingest`.

**Expected**: both nav links remain visible and tappable (wrapping to a second line is
acceptable; disappearing or overlapping content is not).

## Automated coverage

`pytest` covers: new route paths (`tests/test_api.py`, `tests/test_ui.py`,
`tests/test_ingest_upload.py`), nav-link presence on both pages, and `data-step`/`.error`
markup on each ingest-flow response state — see contracts/nav-and-step-ui.md for the exact
hooks asserted against.
