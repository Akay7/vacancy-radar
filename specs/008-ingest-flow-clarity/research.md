# Research: Clear Navigation & Visual Polish for Ingest Flow

No `[NEEDS CLARIFICATION]` markers were left in the Technical Context — this feature reuses the
stack established in [[005-minimal-ui]] (server-rendered Jinja2 + vendored htmx, no build step).
The decisions below cover the choices this feature specifically introduces.

## 1. Route restructuring: `/api/*` for JSON, no prefix for HTML

**Decision**: Move the two JSON endpoints under an `APIRouter(prefix="/api")`
(`POST /api/analyze`, `POST /api/similar`); drop the `/ui/` prefix from the three HTML endpoints
(`POST /analyze`, `POST /ingest/draft`, `POST /ingest/confirm`). `GET /`, `GET /ingest`, and
`GET /healthz` are already unprefixed and stay that way.

**Rationale**: Explicit direction. It also resolves a real inconsistency the current scheme has:
`/analyze` (JSON) and `/ui/analyze` (HTML) look like arbitrary siblings, while `/ingest` (page,
no prefix) and `/ui/ingest/draft` (HTML, prefixed) mix conventions on the *same* feature. One
rule — `/api/*` is the machine-readable contract, everything else is a browser page — is easier
to hold in your head than the current ad hoc mix, which is exactly what this feature is about
fixing.

**Alternatives considered**:
- *Keep the current scheme* — rejected; it's the thing being fixed, and keeping it would leave
  the "which path is the real one" confusion in place.
- *Version the JSON API (`/api/v1/*`)* — rejected; no second API consumer exists yet to justify
  versioning (Constitution IV, YAGNI). Add it if/when an actual second consumer appears.
- *Move `/healthz` under `/api/` too* — rejected; liveness probes are an infra convention
  (Docker/Kubernetes health checks expect a fixed, well-known path) rather than part of the
  "JSON API a client calls for data," which is what `/api/` is meant to denote here.

## 2. Shared layout and navigation via Jinja2 inheritance

**Decision**: Introduce `templates/_layout.html` as a base template (`<head>`, stylesheet link,
`{% include "_nav.html" %}`, a `{% block content %}`) that `index.html` and `ingest.html` both
extend, plus `templates/_nav.html` holding the two persistent links ("Analyze a posting" ↔
"Log a vacancy"). A new `static/style.css` replaces the two pages' currently-duplicated inline
`<style>` blocks.

**Rationale**: FR-001/FR-002 require a nav on *every* page; FR-006 requires shared visual style.
Template inheritance is the standard Jinja2 mechanism for exactly this and requires no new
dependency — `Jinja2Templates` (already wired in `api.py`) supports `{% extends %}`/
`{% include %}` out of the box.

**Alternatives considered**:
- *Duplicate the nav markup and `<style>` block in both templates* — rejected; this is the
  current state, and it's exactly how the two pages drifted into looking unrelated. Duplication
  guarantees the next change only updates one of the two copies.
- *A CSS framework (Bootstrap/Tailwind) or a build step* — rejected (Constitution I/IV): no CDN
  script, no new toolchain, for a two-page app that needs consistent spacing/typography, not a
  component library.

## 3. Step and loading/error state via server-rendered partials, not client JS

**Decision**: Each ingest partial (`ingest.html`, `_ingest_draft.html`, `_ingest_result.html`)
is given a `step` value (`upload` / `review` / `done` / `error`) in its template context, driving
a small shared step-indicator include and a CSS class on the surrounding container. Loading state
during `hx-post` reuses the existing `hx-indicator`/`.htmx-request` pattern already present in
`index.html` (research precedent: [[005-minimal-ui]] `#spinner`). Error responses render with a
distinct `.error` class (icon + color), not plain unstyled text.

**Rationale**: FR-003/FR-004/FR-005 need the *current* step and in-progress/error states to be
visually obvious. Since each of the three ingest routes already returns a distinct, fully
server-rendered partial (`ingest.html` → `_ingest_draft.html` → `_ingest_result.html`), "which
step is active" is already fully determined server-side by which partial is being rendered — no
client-side state needs to be tracked or synchronized.

**Alternatives considered**:
- *A client-side JS state machine tracking the current step* — rejected; the server already
  knows the step (it's choosing which partial to render), so tracking it again in JS would be a
  second source of truth for information the backend already has, with no benefit.
- *Distinguish loading/error purely by wording, no visual/CSS distinction* — rejected; this is
  the current behavior and is exactly what SC-004 ("tell within one glance") requires fixing.

## 4. Nav stays usable at narrow widths without a collapsing menu

**Decision**: The nav is two plain links laid out with CSS flexbox/`flex-wrap`, not a hamburger
menu or a JS-driven toggle.

**Rationale**: FR-008 only requires the nav to remain visible/usable down to 375px — with exactly
two links, wrapping to two lines at narrow widths is sufficient and needs no JS. A collapsing-menu
component would be scope beyond what two links justify (Constitution IV).

**Alternatives considered**: A hamburger/toggle menu — rejected as over-engineered for a
two-item nav; revisit only if a third top-level page is ever added.
