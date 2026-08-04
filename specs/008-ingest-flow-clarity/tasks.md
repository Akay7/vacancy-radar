---

description: "Task list for Clear Navigation & Visual Polish for Ingest Flow"
---

# Tasks: Clear Navigation & Visual Polish for Ingest Flow

**Input**: Design documents from `/specs/008-ingest-flow-clarity/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md,
contracts/route-restructure.md, contracts/nav-and-step-ui.md, quickstart.md

**Tests**: Included — this repo's established pattern (every prior feature: 003/005/006/007) is
tests-first, and Constitution V requires test coverage for new logic. The Foundational phase's
route rename is a mechanical update to *existing* passing tests (no new behavior, so no new
red/green cycle); each user story phase after it adds genuinely new behavior and follows
tests-first.

**Organization**: Tasks are grouped by user story (US1 = P1, US2 = P2, US3 = P3) to enable
independent implementation and testing of each.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root (unchanged from 003/005/006/007).

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Land the route-path restructuring (contracts/route-restructure.md) and the unwired
shared-layout skeleton every user story builds on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 In `src/vacancy_radar/api.py`: create `api_router = APIRouter(prefix="/api")`; move
      the `analyze` and `similar` JSON route functions onto it (unchanged bodies, response
      models, status codes); register it via `app.include_router(api_router)`. Rename the three
      HTML route decorators `@app.post("/ui/analyze")` → `@app.post("/analyze")`,
      `@app.post("/ui/ingest/draft")` → `@app.post("/ingest/draft")`,
      `@app.post("/ui/ingest/confirm")` → `@app.post("/ingest/confirm")` (function bodies/names
      unchanged). Update the module docstring's route summary at the top of the file.
- [X] T002 [P] Update every `client.post("/analyze", ...)` / `client.post("/similar", ...)` call
      in `tests/test_api.py` to `/api/analyze` / `/api/similar`.
- [X] T003 [P] Update every `client.post("/ui/analyze", ...)` call in `tests/test_ui.py` to
      `/analyze`.
- [X] T004 [P] Update every `client.post("/ui/ingest/draft", ...)` /
      `client.post("/ui/ingest/confirm", ...)` call in `tests/test_ingest_upload.py` to
      `/ingest/draft` / `/ingest/confirm`.
- [X] T005 Run `pytest` and confirm every existing test passes again against the new paths
      (mechanical rename verification — no behavior change yet).
- [X] T006 [P] Create `src/vacancy_radar/templates/_layout.html`: `<head>` with a `{% block
      title %}Vacancy Radar{% endblock %}`, `<link rel="stylesheet" href="/static/style.css">`,
      the existing `<script src="/static/htmx.min.js">` tag, then `{% include "_nav.html" %}`
      and `{% block content %}{% endblock %}` in `<body>`.
- [X] T007 [P] Create `src/vacancy_radar/templates/_nav.html` per
      contracts/nav-and-step-ui.md's markup: `<nav class="site-nav">` with an `<a href="/">`
      ("Analyze a posting") and an `<a href="/ingest">` ("Log a vacancy"), each getting an
      `active` class when `active_page` matches (`"analyze"` / `"ingest"`). Not yet included by
      any page other than `_layout.html` itself (US1 wires the pages to extend `_layout.html`).
- [X] T008 [P] Create `src/vacancy_radar/static/style.css` as an empty placeholder file (so
      `_layout.html`'s `<link>` doesn't 404) — populated with real rules in US3.

**Checkpoint**: Route scheme is final and every existing test is green against it; the shared
layout/nav skeleton exists, unwired, ready for the user stories to build on.

---

## Phase 2: User Story 1 - Discover how to log a vacancy from the home screen (Priority: P1) 🎯 MVP

**Goal**: A user on either page has a visible, clickable way to reach the other page — no URL
needs to be typed or already known.

**Independent Test**: quickstart.md Scenario 1 — from `/`, find and follow a link to `/ingest`;
from `/ingest`, find and follow a link back to `/`.

### Tests for User Story 1 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T009 [P] [US1] In `tests/test_ui.py`: `GET /` response body contains
      `<nav class="site-nav">` and an `<a href="/ingest">`.
- [X] T010 [P] [US1] In `tests/test_ingest_upload.py` (wherever `GET /ingest` is already
      tested): response body contains `<nav class="site-nav">` and an `<a href="/">`.

### Implementation for User Story 1

- [X] T011 [US1] Update `src/vacancy_radar/templates/index.html`: change to
      `{% extends "_layout.html" %}`, move the existing `<h1>`/`<p>`/form/`#result` markup into
      `{% block content %}`; change the form's `hx-post` from `/ui/analyze` to `/analyze`. Leave
      the existing inline `<style>` block in place for now (US3 consolidates it into
      `style.css` and removes it — a `<style>` tag left inside `{% block content %}` is valid
      HTML and renders fine as a temporary intermediate state).
- [X] T012 [US1] In `src/vacancy_radar/api.py`'s `index()` handler, pass
      `{"active_page": "analyze"}` into the `index.html` template context.
- [X] T013 [US1] Update `src/vacancy_radar/templates/ingest.html`: change to
      `{% extends "_layout.html" %}`, move its existing `<h1>`/`<p>`/form/`#result` markup into
      `{% block content %}`; change the form's `hx-post` from `/ui/ingest/draft` to
      `/ingest/draft`. Leave its inline `<style>` block in place (same reasoning as T011).
- [X] T014 [US1] In `src/vacancy_radar/api.py`'s `ingest_page()` handler, pass
      `{"active_page": "ingest"}` into the `ingest.html` template context.
- [X] T015 [US1] Update `src/vacancy_radar/templates/_ingest_draft.html`'s confirm-form
      `hx-post` target from `/ui/ingest/confirm` to `/ingest/confirm`.

**Checkpoint**: Both pages render through the shared layout with a working, always-visible nav
between them; every form now targets its final route path. This alone satisfies SC-001/SC-002.

---

## Phase 3: User Story 2 - Understand what step they're on while logging a vacancy (Priority: P2)

**Goal**: The upload/review/confirm steps, plus loading and error states, are each visually and
programmatically distinguishable — never a bare, unchanged form.

**Independent Test**: quickstart.md Scenarios 2 & 3 — upload a file and observe a distinct
loading state, then a distinct "review" state; confirm and observe a distinct "done" state;
trigger a drafting failure and observe a distinct "error" state.

### Tests for User Story 2 ⚠️

> Write these tests FIRST, ensure they FAIL before implementation.

- [X] T016 [P] [US2] In `tests/test_ingest_upload.py`: `GET /ingest` response body contains
      `data-step="upload"`.
- [X] T017 [P] [US2] In `tests/test_ingest_upload.py`: a successful `POST /ingest/draft` (draft
      produced) response body contains `data-step="review"`.
- [X] T018 [P] [US2] In `tests/test_ingest_upload.py`: a failed-draft `POST /ingest/draft` (no
      document text/image, or `LLMProviderError`) response body contains `data-step="error"` and
      wraps the message in `class="error"`.
- [X] T019 [P] [US2] In `tests/test_ingest_upload.py`: a successful `POST /ingest/confirm`
      response body contains `data-step="done"`; a rejected one (validation failure, expired
      upload, conflict) contains `data-step="error"` and wraps the message in `class="error"`.
- [X] T020 [P] [US2] In `tests/test_ui.py`: `_error.html`'s rendered output (from a failed
      `POST /analyze`) wraps its message in `class="error"`.

### Implementation for User Story 2

- [X] T021 [US2] In `src/vacancy_radar/api.py`'s `ingest_draft()`, add
      `"step": "review" if draft else "error"` to the `_ingest_draft.html` template context.
- [X] T022 [US2] In `src/vacancy_radar/api.py`'s `ingest_confirm()`'s inner `result()` helper,
      add `"step": "done" if success else "error"` to the `_ingest_result.html` template
      context.
- [X] T023 [P] [US2] Add `data-step="upload"` (static) to `src/vacancy_radar/templates/ingest.html`'s
      content container; add `hx-indicator="#ingest-spinner"` to its upload form plus an
      `#ingest-spinner` element and matching `#ingest-spinner.htmx-request { display: inline; }`
      rule in its (still-inline, per T011/T013) `<style>` block — mirrors `index.html`'s
      existing `#spinner` pattern so drafting-in-progress is visually distinct (FR-004).
- [X] T024 [P] [US2] Add `data-step="{{ step }}"` to
      `src/vacancy_radar/templates/_ingest_draft.html`'s root container; when `step == "error"`,
      wrap the message in `class="error"`.
- [X] T025 [P] [US2] Add `data-step="{{ step }}"` to
      `src/vacancy_radar/templates/_ingest_result.html`'s root container; wrap the message in
      `class="error"` when `step == "error"`, `class="success"` when `step == "done"`.
- [X] T026 [P] [US2] Update `src/vacancy_radar/templates/_error.html` to wrap its message in
      `class="error"`.

**Checkpoint**: Every ingest-flow state (upload/review/error/done) is both visually distinct and
programmatically identifiable via `data-step`; both flows' error messages share the same
`.error` treatment.

---

## Phase 4: User Story 3 - Recognize the app as one coherent tool (Priority: P3)

**Goal**: `/` and `/ingest` share one visual identity — typography, spacing, buttons, error/nav
styling — instead of two independently-styled pages.

**Independent Test**: quickstart.md Scenario 4 (visual comparison) and Scenario 6 (375px nav
usability).

### Tests for User Story 3 ⚠️

> Write this test FIRST, ensure it FAILS before implementation.

- [X] T027 [US3] In `tests/test_ui.py`: `GET /static/style.css` response contains the `.site-nav`
      and `.error` selectors (fails while `style.css` is still the empty placeholder from T008).

### Implementation for User Story 3

- [X] T028 [US3] Populate `src/vacancy_radar/static/style.css` with the shared rules: base
      typography/spacing (from `index.html`/`ingest.html`'s current inline blocks, consolidated),
      `.site-nav` (flexbox, `flex-wrap: wrap`, an `active` link style — FR-008's 375px floor),
      `.error` (distinct color + icon/label treatment), `.success`, button styling, and the
      `#spinner`/`#ingest-spinner` `.htmx-request` indicator rules carried over from `index.html`
      and `ingest.html`.
- [X] T029 [US3] Remove the now-redundant inline `<style>` blocks from
      `src/vacancy_radar/templates/index.html` and `src/vacancy_radar/templates/ingest.html` —
      all styling now comes from `style.css` via `_layout.html`'s `<link>`.
- [X] T030 [P] [US3] Manual check (quickstart.md Scenario 6): at a 375px viewport width on both
      `/` and `/ingest`, confirm `.site-nav` wraps without overlapping or hiding content; adjust
      `style.css` if it doesn't.

**Checkpoint**: Both pages share one visual identity end to end; the nav stays usable at mobile
widths.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T031 [P] Update `README.md`'s endpoint table and Quick Start section for the new route
      paths (`/analyze`/`/similar` → `/api/analyze`/`/api/similar`; `/ui/analyze` → `/analyze`;
      `/ui/ingest/draft` → `/ingest/draft`; `/ui/ingest/confirm` → `/ingest/confirm`).
- [X] T032 [P] Update `CHANGELOG.md`'s `[Unreleased]` section: `### Changed` — JSON API moved
      under `/api/*`, HTML routes dropped their `/ui/` prefix (breaking relative to `v0.1.0`,
      per plan.md's Constraints); `### Added` — persistent navigation between the two pages, a
      shared visual style, and step/loading/error indicators on the log-a-vacancy flow.
- [X] T033 Run `ruff check .` and fix any lint findings across all files changed by this feature.
- [X] T034 Run the full `pytest` suite and confirm all tests pass (existing + new).
- [X] T035 Perform manual quickstart validation per
      `specs/008-ingest-flow-clarity/quickstart.md` (all 6 scenarios).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately. BLOCKS all user stories.
- **User Story 1 (Phase 2)**: Depends on Phase 1 (route paths, `_layout.html`/`_nav.html`
  existing). No dependency on US2/US3.
- **User Story 2 (Phase 3)**: Depends on Phase 1. Touches `ingest.html`/`_ingest_draft.html` that
  US1 also touches — do Phase 2 before Phase 3 to avoid rework, though the two stories'
  *changes* don't conflict at the line level (nav/extends vs. `data-step`/spinner markup).
- **User Story 3 (Phase 4)**: Depends on Phase 1 (`style.css` placeholder must exist) and
  benefits from Phase 2/3 being done first (T028 consolidates styling that T023-T026 added
  markup for), but could technically start once Phase 1 is done — Phase 2/3 first is recommended
  to avoid re-touching the same templates twice.
- **Polish (Phase 5)**: Depends on all three user stories being complete.

### Within Each Phase

- T001 (api.py route rename) before T002-T004 (test URL updates) before T005 (verification run).
- T006/T007/T008 (new template/CSS files) have no dependency on T001-T005 and can run in
  parallel with them.
- T011/T013 (extend `_layout.html`) before T012/T014 (`active_page` context) don't strictly
  order against each other, but both must land before T009/T010's tests can pass.
- T021/T022 (api.py `step` context) before T023-T026 (templates reading `{{ step }}`).
- T028 (populate `style.css`) before T029 (remove inline `<style>` blocks) — removing the old
  styles before the new ones exist would leave both pages unstyled.

### Parallel Opportunities

- T002, T003, T004 (Phase 1, different test files) — run in parallel.
- T006, T007, T008 (Phase 1, different new files) — run in parallel, and in parallel with the
  T001-T005 route-rename group.
- T009, T010 (US1 tests, different test files) — run in parallel.
- T016, T017, T018, T019, T020 (US2 tests, same/different test files but independent
  assertions) — run in parallel.
- T023, T024, T025, T026 (US2 implementation, different template files) — run in parallel.
- T031, T032 (Polish docs, different files) — run in parallel.

---

## Parallel Example: Phase 1 (Foundational)

```bash
Task: "Update tests/test_api.py to /api/analyze, /api/similar"
Task: "Update tests/test_ui.py to /analyze"
Task: "Update tests/test_ingest_upload.py to /ingest/draft, /ingest/confirm"
Task: "Create src/vacancy_radar/templates/_layout.html"
Task: "Create src/vacancy_radar/templates/_nav.html"
Task: "Create src/vacancy_radar/static/style.css (empty placeholder)"
```

## Parallel Example: User Story 2 implementation

```bash
Task: "Add data-step to ingest.html + ingest spinner"
Task: "Add data-step to _ingest_draft.html"
Task: "Add data-step to _ingest_result.html"
Task: "Add .error class to _error.html"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (route restructuring + unwired layout skeleton).
2. Complete Phase 2: User Story 1 (nav wiring).
3. **STOP and VALIDATE**: quickstart.md Scenario 1 — the core complaint ("no clear path to
   ingest") is already fixed, even before any visual polish or step-state work.
4. This alone delivers SC-001/SC-002; US2 and US3 refine *how good* that experience feels, not
   *whether* the path exists.

### Incremental Delivery

1. Foundational → US1 (validate Scenario 1) → US2 (validate Scenarios 2 & 3) → US3 (validate
   Scenarios 4 & 6) → Polish (validate Scenario 5, full regression).
2. Each phase leaves the app in a fully working, deployable state.

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to its user story for traceability.
- Verify each new-behavior test fails before implementing against it (Phase 1's route-rename
  tasks are the one exception — they update existing tests to match a mechanical rename, not new
  behavior).
- Stop at each checkpoint to validate independently before moving on.
