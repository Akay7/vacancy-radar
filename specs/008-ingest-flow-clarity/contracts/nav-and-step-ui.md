# UI Contract: Navigation and Step State

Not an HTTP contract — this documents the markup/CSS contract between templates so tests can
target stable hooks, and so the shared layout stays the single source of truth for both pages.

## Navigation (`_nav.html`, included by `_layout.html`)

Present on every page (`index.html`, `ingest.html`, and every partial swapped into either page's
result container, since the nav lives in the page shell, not the swapped fragment):

```html
<nav class="site-nav">
  <a href="/" class="{{ 'active' if active_page == 'analyze' else '' }}">Analyze a posting</a>
  <a href="/ingest" class="{{ 'active' if active_page == 'ingest' else '' }}">Log a vacancy</a>
</nav>
```

`active_page` (`"analyze"` | `"ingest"`) is set by `GET /` and `GET /ingest` respectively when
rendering `index.html`/`ingest.html`, so the current page's link is visually distinguished
(FR-007's "pick the right one without trial and error" extends to "know where you already are").

**Test hook**: `<nav class="site-nav">` containing an `<a href="/ingest">` on the home page's
response body, and an `<a href="/">` on the ingest page's response body (FR-001/FR-002).

## Step indicator (ingest partials only)

Each ingest-flow partial's root element carries a `data-step` attribute:

```html
<div data-step="upload">   <!-- ingest.html -->
<div data-step="review">   <!-- _ingest_draft.html, draft succeeded -->
<div data-step="error">    <!-- _ingest_draft.html, draft failed, or _ingest_result.html success=False -->
<div data-step="done">     <!-- _ingest_result.html, success=True -->
```

**Test hook**: assert `data-step="..."` on the response body matching the expected state per
data-model.md's `IngestStep` table (FR-003).

## Error styling (`_error.html`, and error-state ingest partials)

Error messages render inside `<div class="error">` (or reuse `data-step="error"` above for the
ingest flow specifically) — never as bare text appended to the page (FR-005). `_error.html`
(used by the analyze flow) keeps its existing `message` context variable; only the wrapping
element's class changes from unstyled to `.error`.

**Test hook**: assert `class="error"` (or `data-step="error"`) wraps the message text in the
relevant response body.

## Loading state (analyze form only — ingest already has no separate "in progress" screen)

Unchanged from [[005-minimal-ui]]: `hx-indicator="#spinner"` / `#spinner.htmx-request { display:
inline; }`. The ingest upload form (`ingest.html`) gains the same pattern
(`hx-indicator="#ingest-spinner"`) so FR-004's "in-progress state distinct from initial/completed"
applies there too.
