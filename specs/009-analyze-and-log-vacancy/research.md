# Research: Analyze and Log a Vacancy in One Pass

No `[NEEDS CLARIFICATION]` markers were left in the spec. The decisions below resolve the real
design questions this feature raises, most importantly how image-upload analysis can work at all
given retrieval needs text *before* the LLM is even called.

## 1. `POST /api/analyze` (JSON) stays text-only; only the HTML `POST /analyze` gains upload support

**Decision**: Extend only the browser-facing `POST /analyze` route to accept an optional
multipart `file` alongside `jd_text`. `POST /api/analyze` is untouched.

**Rationale**: The spec's user stories are framed entirely around "the Analyze screen" — a
human-facing concept. No JSON consumer has been named that needs to upload a file. Extending the
JSON contract too would mean designing and testing a second upload surface for a need that
doesn't exist yet (Constitution IV, YAGNI).

**Alternatives considered**: Extend both routes symmetrically — rejected; doubles the surface
area (request parsing, error shapes, tests) for zero stated benefit.

## 2. Image uploads need a text stand-in *before* retrieval can run — new `extract_document_text()`

**Decision**: Add `LLMProvider.extract_document_text(image_bytes, image_media_type) -> str` — a
new abstract method both providers implement, using the same "read the image directly" vision
call pattern already established for `draft_vacancy_metadata()`'s image path, but returning
plain text (no JSON schema) rather than structured fields. For an image upload, this text is
used **only** to drive the existing embedding-based `retriever.query_bullets()` /
`query_similar_vacancies()` calls — the actual grounded analysis afterwards is the *exact same*
`run_analysis()` call the paste-text path already uses, unmodified.

**Rationale**: Retrieval (`sentence-transformers` embeddings) fundamentally needs text — there is
no way to embed an image against a text-embedding index. The paste-text and PDF/DOCX/text-upload
paths already have real JD text before calling `run_analysis()`; images are the only case with
none. Rather than inventing a parallel vision-only grounding path (a second, weaker way of
producing a report — the thing FR-002/FR-008 explicitly guard against), extraction-then-reuse
means images and text end up on the *identical* grounded pipeline, just with one extra step to
get there.

**Is this OCR again?** No — this is the LLM's own vision capability reading the image, the same
category of thing [[007-vision-drafting]] already established for drafting (and explicitly kept:
"the model reads the image directly"). What [[007-vision-drafting]] removed was *local, heuristic*
OCR (`pytesseract`) as a preprocessing/fallback step. Asking the already-configured vision model
to transcribe the posting is a direct continuation of that same principle, not a reversal of it.

**Alternatives considered**:
- *Use the drafted company/position/date as a coarse retrieval query* (e.g. `"{position} at
  {company}"`) — rejected; retrieval quality (bullet recall, similar-vacancy precision — both
  metrics the eval harness measures for the text path) would degrade badly for image uploads
  specifically, and Constitution II treats grounding quality as non-negotiable, not a
  nice-to-have.
- *Extend `analyze()` itself with `image_bytes`/`image_media_type` params, mirroring
  `draft_vacancy_metadata()`* — rejected; this would require the vision model to also select
  which bullets to cite *without ever having been given any bullets* (since none can be
  retrieved before the call), which breaks Constitution II's citation requirement entirely for
  images. Extract-then-retrieve-then-analyze is the only order that keeps grounding intact.

## 3. Two LLM calls for an image upload, not one — accepted, not optimized away

**Decision**: An image upload on the Analyze screen costs three LLM calls total: text
extraction (new), the existing grounded `analyze()` call, and the existing `draft_vacancy_metadata()`
vision call. No attempt is made to combine any of these into fewer calls.

**Rationale**: This is a single-user, interactive, low-frequency action (someone analyzing one
posting they're about to apply to) — not a hot path with a latency/cost budget to protect
(Constitution IV: infra should match real load, and there's no real load pressure here).
Combining calls would mean designing a single vision prompt that both transcribes the posting
*and* proposes match_band/flags/gaps grounded in bullets it was never given up front — the same
ordering problem research.md #2 already ruled out.

**Alternatives considered**: A single combined vision call producing extraction + draft fields
together — rejected for the reason above (the grounding-order problem), plus it would couple two
independently-failable concerns (drafting, text extraction) into one request, undermining FR-007's
requirement that each can fail independently.

## 4. Combined view via template composition, not a new page

**Decision**: `_report.html` gains one small conditional block —
`{% if upload_token %}...{% include "_ingest_draft.html" %}{% endif %}` — rendered only when the
Analyze route was given a file (and therefore has an `upload_token` to pass through). The paste-
text call path passes no `upload_token` (defaults to `None`/absent), so `_report.html`'s output
for that case is byte-for-byte unchanged from today (FR-006).

**Rationale**: `_ingest_draft.html` already renders the exact form (`hx-post="/ingest/confirm"`)
this feature needs — reusing it via `{% include %}` means the save step requires *zero* new
template or route code (FR-008's "identical behavior" is automatic, not something to keep in
sync by hand).

**Alternatives considered**: A new `_analyze_with_upload_result.html` template composing both
partials — rejected; an `{% include %}` on the existing report template achieves the same result
with one new line instead of a new file plus wiring for a second code path.

## 5. Startup-time LLM config validation — a real bug, not just hardening

**Decision**: Add a FastAPI `lifespan` context manager that calls a new
`validate_llm_provider_config()` before the app finishes starting. For `LLM_PROVIDER=claude`
(the default), it checks `ANTHROPIC_API_KEY` is set and non-empty; if not, it raises with a
specific message, which FastAPI/uvicorn surfaces by failing to start the process (non-zero
exit) rather than silently accepting requests. Ollama needs no equivalent check — `OLLAMA_HOST`/
`OLLAMA_MODEL` both have working defaults and there is no secret to be missing.

**Rationale — confirmed as a live bug, not a hypothetical**: `anthropic.Anthropic()` does **not**
validate the API key at construction (`api_key` is simply `None` if unset). The first real call
(`messages.create()`) then raises a bare `TypeError` ("Could not resolve authentication
method...") — verified directly against the installed `anthropic` SDK — which is **not** one of
the exception types `ClaudeProvider`'s existing `except (anthropic.APIConnectionError,
anthropic.AuthenticationError)` blocks catch. Today, an unset `ANTHROPIC_API_KEY` therefore
produces an unhandled 500 with a raw traceback on the *first* request to any LLM-backed route,
not the intended `LLMProviderError` → friendly-message path. Catching `TypeError` there was
considered and rejected as too broad (it would also swallow unrelated programming errors);
validating presence up front, once, is the precise fix for the actual failure mode.

**Alternatives considered**:
- *Catch `TypeError` in the provider's exception handlers* — rejected; too broad a catch for an
  LLM-call wrapper, risks masking real bugs unrelated to authentication.
- *Check in `cli.py`'s `serve` subcommand before calling `uvicorn.run()`* — rejected in favor of
  `lifespan`, since `lifespan` also covers running the app via a direct `uvicorn` invocation
  (e.g. `uvicorn vacancy_radar.api:app`) or any future entry point, not only the `serve` CLI
  command specifically.
- *Check on every request inside `get_llm_provider()`* — rejected; this is a one-time setup
  problem (FR-010 explicitly frames it that way), not a per-request concern, and checking once
  at startup is cheaper and fails faster (before the server even starts accepting traffic).

**Test-suite impact**: FastAPI only runs `lifespan` when `TestClient` is used as a context
manager (`with TestClient(app) as client:`); the existing suite's module-level
`client = TestClient(app)` calls never trigger it, so no existing test needs a fake
`ANTHROPIC_API_KEY` to keep passing — confirmed by inspecting every existing test file's
`TestClient` usage.
