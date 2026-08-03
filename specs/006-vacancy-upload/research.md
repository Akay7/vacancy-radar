# Phase 0 Research: Vacancy Document Upload

## 1. `data/user` mount: read-only → read-write

**Decision**: Change `docker-compose.yml`'s `./data/user:/data/user:ro` to `./data/user`
(read-write). `./data/example:/data/example:ro` stays read-only.

**Rationale**: Confirmed directly with the user after surfacing the conflict during planning.
Constitution VI requires the confirmed vacancy to land in git-trackable source, not only in
Chroma — otherwise a `reindex` (which rebuilds Chroma purely from source) would silently erase
any vacancy this feature ever created. Since the containerized deployment previously had zero
write path to source data, mounting `data/user` read-only was a reasonable earlier choice with
no downside — this feature is the first legitimate reason to change that. `data/example` never
needs writing (it's fixed demo/CI fixture data) and stays read-only.

**Alternatives considered**: Write confirmed vacancies to a separate writable staging directory
and require the maintainer to manually move them into their real `VACANCY_DIR` afterward —
rejected per the user's explicit choice; it would satisfy Constitution VI eventually but not
immediately, and adds a manual step FR-005 is meant to eliminate.

## 2. Local text extraction: which libraries, per format

**Decision**:
- **PDF**: `pypdf` — reads the embedded text layer directly. If a PDF has no extractable text
  (e.g., it's a scanned image with no OCR layer), extraction yields empty/near-empty text; this
  is treated the same as any other unreadable document (FR-008's edge case — clear message,
  fall back to manual entry). No OCR-on-scanned-PDF pipeline is built for this feature.
- **DOCX**: `python-docx` — reads paragraph text directly; DOCX is a structured XML format with
  no OCR concerns.
- **Images** (PNG/JPEG, e.g. a phone photo or screenshot of a posting): `pytesseract` +
  `Pillow`. `pytesseract` is a thin Python wrapper; the actual OCR engine is the system
  `tesseract-ocr` binary, a new OS-level dependency (`apt-get install tesseract-ocr` in
  `Dockerfile`; already present in this dev environment for manual validation, per `tesseract
  --version` → 5.5.3).
- **Plain text** (`.txt`, `.md`): read directly, no extraction library needed — matches how
  `sources/`/`correspondence/` already handle text files today.

**Rationale**: All three are standard, actively-maintained, pure-local libraries (no network
call, no paid API) — consistent with Constitution I. Each handles exactly one format well rather
than reaching for a heavier all-in-one document-conversion toolkit, consistent with Constitution
IV (YAGNI): this feature needs "get readable text out of a single small document," not a general
document-processing pipeline.

**Alternatives considered**: A cloud OCR/document-intelligence API — rejected outright, violates
Constitution I. `pdfplumber` instead of `pypdf` for PDFs — rejected as heavier than needed for
plain text-layer extraction (pdfplumber's extra layout-analysis features aren't needed here).

## 3. How metadata gets drafted from extracted text

**Decision**: Add one new method to the `LLMProvider` abstract base class,
`draft_vacancy_metadata(document_text: str) -> DraftVacancyMetadata`, implemented by both
`ClaudeProvider` (via `output_config.format` structured JSON, same pattern as `analyze()`) and
`OllamaProvider` (via `format: "json"` + one retry, same pattern as `analyze()`). Both providers
only ever receive plain extracted text — never the original image/PDF/DOCX bytes directly.

**Rationale**: Constitution III requires both providers to work uniformly through the same
interface. Claude's API can accept images/PDFs directly (native vision), but ordinary local
Ollama models generally can't, and `OllamaProvider`'s existing implementation has no image
handling at all. Extracting text locally *before* the LLM call — rather than sending raw
document bytes to whichever provider is configured — means there is no vision-only-works-with-
Claude asymmetry to design around: by the time either provider is invoked, the input shape
(plain text) is identical to what `analyze()` already sends today.

**Alternatives considered**: Send the image/PDF directly to Claude's vision API when using
`ClaudeProvider`, falling back to OCR only for `OllamaProvider` — rejected: this would mean the
two providers behave differently for the same uploaded document (different accuracy, different
failure modes), undermining the "both remain functional through the same interface" guarantee
Constitution III is built around, for no real gain here (the documents in scope are short —
a single posting or offer — where OCR/text-layer extraction is already sufficient).

## 4. The two-step draft → confirm flow and where the upload lives in between

**Decision**: `POST /ui/ingest/draft` accepts the uploaded file, writes it to
`.cache/pending-uploads/<uuid>/<original-filename>`, extracts its text, calls
`draft_vacancy_metadata()`, and renders an editable review form whose hidden fields carry the
`<uuid>` staging token (not the file content itself). `POST /ui/ingest/confirm` reads the
maintainer's (possibly edited) field values plus the token, re-locates the staged file, moves it
into the new vacancy folder's `sources/`, and deletes the now-empty staging directory.

**Rationale**: HTTP is stateless and this is inherently a two-request flow (draft, then
confirm) — the uploaded bytes need to live *somewhere* server-side in between without asking the
maintainer to re-upload the same file on confirm. `.cache/` is already this project's designated
disposable-scratch location (the ingest manifest and the Chroma store both already live there);
a staging subdirectory keyed by a random token fits the same convention and needs no new
infrastructure. An abandoned draft (uploaded, never confirmed) leaves a harmless orphaned
directory under `.cache/`, consistent with `.cache/` already being safe to delete at any time —
no expiry/cleanup job is built for this (YAGNI); it's an acceptable, bounded amount of litter for
a single-user local tool.

**Alternatives considered**: Re-upload the file again on confirm (no server-side staging at
all) — rejected, poor UX (the maintainer would have to pick the file twice) and no simpler to
implement. Keep the file in server memory/session state between requests — rejected, the app is
otherwise fully stateless between requests and a memory-based approach doesn't survive a server
restart between draft and confirm, whereas a `.cache/` file does.

## 5. Writing the confirmed vacancy and reusing existing ingestion logic

**Decision**: On confirm, compute the natural key from the (edited) company/position/date
fields using the existing `ingest.natural_key()`/`slugify()` functions unchanged, create
`VACANCY_DIR/<natural-key>/`, write `vacancy.yaml` (company/position/date/outcome — the same
four fields, same format, [[001-ingestion-cli]]'s existing schema, nothing new), move the staged
document into `<natural-key>/sources/<original-filename>`, then call the existing
`ingest.ingest_vacancies(vacancy_dir, ...)` function again over the whole `VACANCY_DIR` — exactly
as `sync` already does — to upsert the new folder into Chroma.

**Rationale**: `ingest_vacancies()` already implements natural-key computation, conflict
detection (FR-009 from [[001-ingestion-cli]]), and idempotent upsert for every folder under
`VACANCY_DIR`. Re-invoking it after writing one new folder gets all of that for free, and
guarantees this feature can never drift from how the CLI path already behaves — there is exactly
one place vacancy-folder-to-Chroma upsert logic exists, not two parallel implementations.
Detecting a natural-key conflict (FR-006) is then just reading `RunSummary.vacancies_conflicting`
from that same call and surfacing it to the maintainer, rather than writing new conflict-
detection logic.

**Alternatives considered**: Write a bespoke single-vacancy upsert path directly into Chroma from
the confirm route, skipping the folder-write step — rejected outright, this is exactly the
Constitution VI violation the read-only-mount discovery (research.md #1) exists to prevent.

## 6. Date field when it can't be determined from the document

**Decision**: When `draft_vacancy_metadata()` can't determine a posting date from the extracted
text, the draft form pre-fills the date field with today's date (the day the maintainer is
logging the vacancy), still editable before confirming.

**Rationale**: A job posting frequently doesn't state its own publish date in a
machine-obvious way, but "today" is exactly the same reasonable default a maintainer would type
by hand in this situation — it's not a fabricated fact being presented as extracted (the field
stays editable and the maintainer sees today's date, not a disguised guess), just a sensible
starting point.

## 7. Testing strategy for extraction and OCR quality

**Decision**: `tests/test_documents.py` exercises `extract_text()` against small fixtures
synthesized at test time — `python-docx` to build a one-paragraph DOCX, `Pillow` to render a
short string to a PNG, and (**corrected during implementation** — `pypdf` turned out to have no
text-drawing/canvas API at all, only page/metadata manipulation; verified by inspecting
`PdfWriter`'s actual methods before committing to this) `reportlab`, added as a **dev-only**
test dependency, to build a one-page PDF with known text — not hand-curated binary files checked
into the repo. `LLMProvider.draft_vacancy_metadata()` is faked in route-level tests exactly like
`analyze()` already is. Genuine OCR accuracy against a *real* photographed/screenshotted posting,
and real-world PDF/DOCX quirks, are validated once for real in the manual quickstart pass —
consistent with this project's established pattern ([[003-analyze-report-generation]],
[[005-minimal-ui]]) of reserving a real, non-faked pass for exactly the boundary a fake can't
meaningfully stand in for.

**Alternatives considered**: Mock `pytesseract`/`pypdf`/`python-docx` entirely in unit tests —
rejected as it would leave the actual extraction code paths themselves unverified; synthesizing
real (if trivial) files exercises the real library calls while staying fast and deterministic.

## 8. FastAPI `Form(...)` (required) rejects an empty string as "missing", not as a value

**Discovered during implementation**: `POST /ui/ingest/confirm` needs to reject an empty
`outcome` (and, more generally, any blank field) with a friendly rendered message — but
declaring `outcome: str = Form(...)` causes FastAPI to respond with a raw `422 {"detail":
[{"type": "missing", ...}]}` *before* the route body ever runs, whenever the submitted value is
an empty string. Verified directly with a minimal isolated repro (a two-line FastAPI route) to
confirm this is genuine platform behavior, not a bug in this project's code: a required
`Form(...)` parameter treats `""` the same as the field being absent entirely.

**Decision**: Declare `company`, `position`, `date`, and `outcome` as `Form("")` (not required,
defaulting to empty string) and validate their presence explicitly inside the route body,
returning the same rendered `_ingest_result.html` message for a blank field as for any other
input problem. `upload_token`/`original_filename` stay `Form(...)` — they're hidden fields
always populated by the previous render step, not something a maintainer directly leaves blank.

**Rationale**: The route's contract promises "always `200 OK`, rendered HTML" — letting the
platform's own required-field check short-circuit that with a raw JSON `422` for the one field
(`outcome`) this feature most needs to validate would directly contradict it.

## 9. Retiring `POST /ingest/vacancy` instead of redefining it

**Corrected during implementation**: the original plan (see this document's earlier framing)
was to redefine `POST /ingest/vacancy`'s contract in place, since the M1-scaffold stub (a bare
`vacancy_folder: str` path parameter, for a different, never-built idea) had only ever returned
`501`. While implementing the routes, [[005-minimal-ui]]'s existing `/ui/analyze` naming
convention (an HTML-rendering route living alongside its JSON counterpart, `/analyze`) turned
out to fit this feature better than reusing the old path — so `GET /ingest` +
`POST /ui/ingest/draft` + `POST /ui/ingest/confirm` were added as genuinely new routes, and the
dead `POST /ingest/vacancy` stub was removed from `api.py` entirely rather than left sitting
alongside them as orphaned, confusingly-named dead code.

**Rationale**: Keeping an always-`501`, never-reachable-in-practice stub around once real
routes exist elsewhere would be exactly the kind of leftover cruft this project has otherwise
been careful to avoid (Constitution IV).
