# Implementation Plan: Clear Navigation & Visual Polish for Ingest Flow

**Branch**: `008-ingest-flow-clarity` | **Date**: 2026-08-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-ingest-flow-clarity/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Close the discoverability and consistency gap named in the spec: today `/` (analyze) and
`/ingest` (log a vacancy) are two unstyled, disconnected pages with no link between them, and the
ingest flow gives no visual sense of which step (upload/review/done) is active. This plan adds a
persistent nav shared by both pages, a shared stylesheet/layout so both read as one app, and
step/loading/error state markup on the ingest partials — no new dependencies, same server-rendered
Jinja2 + vendored-htmx stack established in [[005-minimal-ui]]. Alongside this, per explicit
direction, the route scheme is restructured: the JSON API moves under an `/api/` prefix
(`/api/analyze`, `/api/similar`) and the HTML routes drop the `/ui/` prefix entirely
(`/analyze`, `/ingest/draft`, `/ingest/confirm`) — producing one guessable rule ("`/api/*` is the
machine contract, everything else is a page") instead of today's inconsistent mix where `/ui/`
sometimes appears and sometimes doesn't.

## Technical Context

**Language/Version**: Python 3.11 (unchanged).

**Primary Dependencies**: None new. Reuses FastAPI (adding an `APIRouter(prefix="/api")` to
express the route split — already part of the installed `fastapi` package, not a new
dependency), Jinja2 template inheritance (already in use, just newly leaning on `{% extends %}`/
`{% include %}` instead of duplicating full-page markup), and the existing vendored
`static/htmx.min.js`.

**Storage**: N/A — no new persisted or cached state; this is presentation/navigation/routing only.

**Testing**: `pytest` + FastAPI's `TestClient`, same pattern as every prior feature — existing
route-path assertions in `tests/test_api.py`, `tests/test_ui.py`, `tests/test_ingest_upload.py`
are updated to the new paths, and new assertions cover nav-link presence and step-state markup.

**Target Platform**: Same as today — single `app` service, no new container/port.

**Project Type**: Web application — single FastAPI project (unchanged).

**Performance Goals**: No change — this feature touches only routing and rendered markup, not
the retrieval/generation pipeline's latency.

**Constraints**: The `/api/analyze` and `/api/similar` JSON request/response bodies must stay
byte-for-byte identical to today's `/analyze`/`/similar` — only the URL path moves. This *is* a
breaking change relative to the already-tagged `v0.1.0` (which documented `/analyze`/`/similar`
as the public JSON paths and `/ui/analyze`/`/ui/ingest/*` as the HTML paths) — the CHANGELOG for
the next release must call this out under `### Changed`, since `v0.1.0` is a real prior release
to diff against this time (unlike `v0.1.0` itself, which had nothing prior).

**Scale/Scope**: Two page templates gain a shared layout/nav, one new shared stylesheet, three
existing HTML routes get new paths (prefix dropped), two existing JSON routes get new paths
(prefix added), three ingest partials gain step/state markup — no new pages, no new backend
logic.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Local-First & Private by Default | No change to data handling; nav/style/step markup is static local markup, no third-party script or CDN request added. | PASS |
| II. Grounded Generation (NON-NEGOTIABLE) | Not touched — `run_analysis()`/`grounding.enforce()` are unchanged; only the route path calling into them moves. | PASS |
| III. Pluggable, Provider-Agnostic LLM | Not touched — routes still resolve `LLMProvider` via `get_llm_provider()` exactly as today. | PASS |
| IV. Simplicity & Right-Sized Infra (YAGNI) | No new dependency, no new service, no build step. The route-prefix split uses `APIRouter`, already part of FastAPI; the shared layout uses Jinja2 inheritance, already the templating engine in use. Nav is two plain links (no hamburger menu/JS toggle) since there are only two pages to link between. | PASS |
| V. Test & Lint Gates | Existing route-path assertions across `test_api.py`/`test_ui.py`/`test_ingest_upload.py` must be updated as part of this change (not optional — they'd otherwise fail against the new paths); new tests cover nav links and step markup. | PASS |
| VI. Regenerable Derived State | Not touched. | PASS |

No violations to justify — Complexity Tracking section left empty.

*Re-checked post-Phase 1 (after research.md/data-model.md/contracts/quickstart.md were written):
unchanged — the route restructuring and shared-layout/step-state additions remain purely
routing/presentation moves with no new principle exposure.*

## Project Structure

### Documentation (this feature)

```text
specs/008-ingest-flow-clarity/
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
├── api.py                     # restructured: api_router = APIRouter(prefix="/api") holds
│                               #   analyze/similar (JSON); un-prefixed /analyze, /ingest/draft,
│                               #   /ingest/confirm now serve the HTML routes (prefix dropped);
│                               #   GET /, GET /ingest, GET /healthz unchanged
├── templates/
│   ├── _layout.html            # NEW: shared <head>/style-link/nav base; index.html + ingest.html extend it
│   ├── _nav.html                # NEW: persistent nav partial (Analyze <-> Log a vacancy links), included by _layout.html
│   ├── index.html               # extended: now `{% extends "_layout.html" %}`, form posts to /analyze
│   ├── ingest.html               # extended: now `{% extends "_layout.html" %}`, form posts to /ingest/draft, step=upload
│   ├── _ingest_draft.html        # extended: step-indicator markup (step=review), posts to /ingest/confirm
│   ├── _ingest_result.html       # extended: step-indicator markup (step=done/error)
│   ├── _report.html              # unchanged content — inherits shared style via _layout.html's stylesheet link
│   └── _error.html               # extended: distinct `.error` styling class/icon (FR-005)
└── static/
    ├── style.css                 # NEW: shared stylesheet — replaces the inline <style> blocks
    │                              #   currently duplicated in index.html and ingest.html
    ├── htmx.min.js                # unchanged
    └── ui.js                      # unchanged

tests/
├── test_api.py                   # updated: JSON routes now POST /api/analyze, POST /api/similar
├── test_ui.py                    # updated: HTML analyze route now POST /analyze (was /ui/analyze);
│                                  #   new assertions for nav links on both pages
├── test_ingest_upload.py         # updated: POST /ingest/draft, POST /ingest/confirm (was /ui/ingest/*);
│                                  #   new assertions for step markup on each partial
```

README.md's endpoint table and Quick Start, and CHANGELOG.md, are updated to the new paths as
part of implementation (not new source, so not listed above) — see quickstart.md.

**Structure Decision**: Single project (unchanged) — everything stays inside the existing
`src/vacancy_radar` package served by the one FastAPI app, consistent with every prior feature's
"no separate frontend project" decision (`[[005-minimal-ui]]`). The only structural addition is
splitting `api.py`'s routes across an `/api`-prefixed `APIRouter` and the app's existing
un-prefixed routes — still one file, one process, one deployable unit.

## Complexity Tracking

> No violations — this section is intentionally empty; see the Constitution Check table above.
