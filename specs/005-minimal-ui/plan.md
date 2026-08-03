# Implementation Plan: Minimal UI

**Branch**: `005-minimal-ui` | **Date**: 2026-08-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-minimal-ui/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add a server-rendered HTML UI directly to the existing FastAPI app: one page where a user pastes
job-description text, submits it via an HTMX-powered form (no page reload), and sees the
rendered match report — score, flags, gaps, similar vacancies, and a draft paragraph with each
sentence's citation shown inline. No new service, no new build toolchain, no frontend
framework — per the user's explicit direction to add no extra dependencies beyond what's
minimally required to serve HTML/forms from FastAPI itself: `jinja2` (already present
transitively, now declared directly) and `python-multipart` (genuinely new, required
unconditionally by FastAPI's form-parsing support), plus a locally-vendored copy of htmx that
needs no build step or package manager. The existing JSON `POST /analyze`
contract is untouched; the orchestration it performs is extracted into a shared function so the
new HTML route reuses it instead of duplicating it, and a small additive field is added to
`Report` so the draft paragraph's per-sentence grounding is structurally visible to a template,
not just implied by two separately-ordered flat lists.

## Technical Context

**Language/Version**: Python 3.11 (unchanged) + server-rendered Jinja2 HTML templates + one
vendored, unbuilt JavaScript file (HTMX) for form submission without a full page reload.

**Primary Dependencies**: `jinja2` (add as an explicit direct dependency — already present
transitively today, per `python -c "import jinja2"` succeeding against the existing lockfile,
but never declared; using it directly means declaring it, per research.md) and
`python-multipart` (a genuinely new, small dependency — verified that FastAPI's `Form(...)`
parameter support requires it unconditionally to parse any form body, not only file uploads;
there's no way around it short of hand-rolling form parsing, per research.md). HTMX is vendored
as a single static `.js` file checked into the repo, not an npm/pip package — no new toolchain,
no CDN request at runtime (Constitution I).

**Storage**: N/A — no new persisted or cached state; the UI is a presentation layer over the
existing `POST /analyze` response.

**Testing**: `pytest` + FastAPI's existing `TestClient`, same pattern already used for
`/analyze`/`/similar` — new tests assert on rendered HTML content (e.g. via substring/selector
checks), not a new test framework.

**Target Platform**: Same as today — runs inside the existing single `app` service in
`docker-compose.yml`; no new container, no new port.

**Project Type**: Web application — but staying a *single* FastAPI project (not a separate
frontend/backend split), since the UI is server-rendered from the same process that already
serves the JSON API.

**Performance Goals**: Page and form both load/submit with no perceptible overhead beyond
`/analyze`'s own LLM-bound latency (unchanged) — HTMX's partial swap avoids a full page reload
but doesn't change how long the underlying analysis takes.

**Constraints**: No new external service, no CDN-hosted script at runtime (Constitution I), no
new heavy dependency (Constitution IV), the existing JSON `POST /analyze` response shape must
stay backward-compatible (only additive fields).

**Scale/Scope**: One page, three Jinja2 templates (shell, report partial, error partial), one
vendored JS file, a handful of new/extended routes and one small additive backend field — sized
to "minimal UI," not a general-purpose frontend.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | UI served entirely from the user's own local backend; HTMX vendored locally, not CDN-linked; no analytics/third-party script; posting text/report contents never leave the local process. | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | FR-003 requires the draft paragraph's grounding to be *visible*, not just enforced silently — this plan adds a small additive `Report.draft_sentences` field (research.md) so the UI can show each sentence next to its citation, strengthening (not weakening) grounding's visibility. | PASS |
| III. Pluggable, Provider-Agnostic LLM | The UI never calls an `LLMProvider` directly — it calls the same shared `run_analysis()` function the JSON route calls, which resolves the provider exactly as today. | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | No new service, no new build step, no new heavy dependency; HTMX is a single vendored file; `jinja2` is only made an explicit dependency for something already transitively present. | PASS |
| V. Test & Lint Gates | New routes/templates get `pytest` coverage against rendered HTML; `ruff` unaffected (Python-only lint scope). | PASS |
| VI. Regenerable Derived State | N/A — no new derived/cached state introduced by this feature. | PASS |

No violations to justify — Complexity Tracking section left empty.

*Re-checked post-Phase 1 (after research.md/data-model.md/contracts/quickstart.md were
written): unchanged — the `draft_sentences` addition and shared `run_analysis()` extraction are
both purely additive/refactoring moves with no new principle exposure.*

## Project Structure

### Documentation (this feature)

```text
specs/005-minimal-ui/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/vacancy_radar/
├── api.py                    # extended: GET /, POST /ui/analyze; run_analysis() extracted
│                              # and reused by both POST /analyze (JSON) and POST /ui/analyze (HTML)
├── grounding.py               # extended: enforce() also returns structured draft_sentences
├── models.py                  # extended: DraftSentence; Report gains draft_sentences field
├── templates/
│   ├── index.html             # page shell: the paste-JD form
│   ├── _report.html            # partial: rendered report (flags/gaps/similar/draft+citations)
│   └── _error.html             # partial: validation / backend-unavailable messages
└── static/
    ├── htmx.min.js             # vendored, unbuilt — no package manager, no CDN request
    └── ui.js                   # copy-to-clipboard handler (User Story 2)

tests/
├── test_ui.py                 # new: GET /, POST /ui/analyze rendering + error-state tests
├── test_grounding.py           # extended: draft_sentences pairing
└── test_api.py                # extended: Report.draft_sentences present, JSON shape otherwise unchanged
```

**Structure Decision**: Single project (unchanged) — the UI is added directly into the existing
`src/vacancy_radar` package and served by the same FastAPI app, per the user's direction to add
no new dependencies/toolchain. Both `templates/` and `static/` live *inside* the
`src/vacancy_radar` package, next to `api.py` that serves them — not at the repo root, since
these are assets of the FastAPI app itself, not project-level config (contrast with
`data/`, `eval/`, which are genuinely repo-root concerns unrelated to any one Python package).
`app.mount("/static", ...)` still exposes them at the URL path `/static/...`; only the
filesystem source location changes. There is no separate `frontend/` project because there is
no separate frontend service.

## Complexity Tracking

> No violations — this section is intentionally empty; see the Constitution Check table above.
