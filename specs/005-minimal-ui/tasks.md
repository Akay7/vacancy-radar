---

description: "Task list for Minimal UI feature implementation"
---

# Tasks: Minimal UI

**Input**: Design documents from `/specs/005-minimal-ui/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/ui-routes.md](./contracts/ui-routes.md), [quickstart.md](./quickstart.md)

**Tests**: Included — Constitution Principle V ("Test & Lint Gates") requires test coverage for
new routes/templates, same as every prior feature in this project.

**Organization**: Tasks are grouped by user story (US1-US3, matching spec.md's P1-P3). Per the
user's explicit direction, no new frontend framework or build toolchain is introduced — only
`jinja2`, `python-multipart` (both required for FastAPI to serve/parse HTML forms at all, per
research.md), and one vendored, unbuilt `htmx.min.js`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to the repository root

## Path Conventions

Single project — `src/vacancy_radar/`, `tests/` at repository root, per plan.md's Structure
Decision. `templates/` and `static/` both live *inside* `src/vacancy_radar/`, next to `api.py`
that serves them — they're assets of the FastAPI app, not repo-root config. Reuses
`data/example/` fixtures already created by [[001-ingestion-cli]] — no new fixture data needed.
LLM calls are faked in automated tests (same dependency-injection pattern as
`tests/test_api.py`); real backend validation only happens in the manual quickstart pass
(Phase 6).

---

## Phase 1: Setup

- [x] T001 Add `"jinja2>=3.1"` and `"python-multipart>=0.0.9"` to `[project].dependencies` in
      `pyproject.toml`; sync the lockfile (`uv sync --extra dev` or equivalent) — research.md #2
- [x] T002 [P] Create the `src/vacancy_radar/templates/` and `src/vacancy_radar/static/`
      directories (per plan.md's Structure Decision)
- [x] T003 [P] Vendor htmx into `src/vacancy_radar/static/htmx.min.js` (checked-in file, not a
      CDN reference or an npm/pip package) — research.md #1
- [x] T004 In `src/vacancy_radar/api.py`, resolve both directories relative to the module's own
      location — `BASE_DIR = Path(__file__).resolve().parent`, then
      `Jinja2Templates(directory=BASE_DIR / "templates")` and
      `app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")` — not a
      literal `"src/vacancy_radar/..."` string, which would only work by coincidence of the
      process's current working directory (the Dockerfile's `pip install .` installs the
      package, then runs `uvicorn` from `/app`, where `./src/...` happens to still exist — a
      `__file__`-relative path works regardless of CWD or install method) — depends on T001,
      T002, T003

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The additive `draft_sentences` data shape and the shared analysis function every
user story's routes call — nothing UI-specific can be built until these exist.

**⚠️ CRITICAL**: No user story implementation can begin until this phase is complete.

- [x] T005 [P] Add `DraftSentence` model (`text: str`, `citation: Citation`) to
      `src/vacancy_radar/models.py`; add `draft_sentences: list[DraftSentence]` to `Report`,
      after the existing `draft_paragraph` field — data-model.md
- [x] T006 Add `draft_sentences: list[DraftSentence]` to the `GroundedContent` dataclass in
      `src/vacancy_radar/grounding.py`; in `enforce()`'s existing draft-sentence loop, append one
      `DraftSentence(text=sentence.text, citation=Citation(quote=sentence.quote,
      source_id=sentence.source_id))` alongside each already-kept sentence, so
      `draft_paragraph == " ".join(d.text for d in draft_sentences)` holds — depends on T005
- [x] T007 Extract `run_analysis(jd_text: str, retriever: Retriever, llm_provider: LLMProvider)
      -> Report` in `src/vacancy_radar/api.py` from the existing `/analyze` route body
      (retrieval, `load_filter_rules()`, `llm_provider.analyze()`, `grounding.enforce()`, and
      `Report` assembly — now including `draft_sentences=grounded.draft_sentences`); update the
      `/analyze` route to keep only the empty-input `422` check and the
      `LLMProviderError`/`ValidationError`/`json.JSONDecodeError` → `502` handling around a call
      to `run_analysis()` — depends on T006

**Checkpoint**: Foundation ready — user story implementation can now begin, in any order.

---

## Phase 3: User Story 1 - Paste a posting, see the full match report (Priority: P1) 🎯 MVP

**Goal**: `GET /` serves the paste-JD form; submitting it renders the full match report (score,
flags, gaps, similar vacancies) in place, without a full page reload.

**Independent Test**: With the backend running and `data/example/` ingested, open the page,
paste a job posting, submit it, and confirm the rendered report matches what a direct
`POST /analyze` call with the same text returns.

### Tests for User Story 1

- [x] T008 [P] [US1] Test `grounding.enforce()` populates `draft_sentences`, pairing each kept
      `CandidateSentence` with the same citation that already appears in `citations`/
      `draft_paragraph`, in `tests/test_grounding.py`
- [x] T009 [P] [US1] Test `GET /` returns `200` and renders a form with a `jd_text` textarea, in
      `tests/test_ui.py`
- [x] T010 [P] [US1] Test `POST /ui/analyze` with a valid JD (fake `LLMProvider` dependency
      override, same pattern as `tests/test_api.py`) returns `200` HTML containing the match
      band, at least one flag's label and reason, the gaps, and a similar vacancy's
      company/outcome, in `tests/test_ui.py`
- [x] T011 [P] [US1] Test `POST /analyze`'s JSON response now includes `draft_sentences`
      matching the sentences in `draft_paragraph`, and every field asserted by
      [[003-analyze-report-generation]]'s existing tests is unchanged, in `tests/test_api.py`

### Implementation for User Story 1

- [x] T012 [US1] Create `src/vacancy_radar/templates/index.html`: page shell with a
      `<textarea name="jd_text">` form using `hx-post="/ui/analyze" hx-target="#result"`, an
      empty `#result` container, and `<script src="/static/htmx.min.js">` — depends on T004
- [x] T013 [US1] Create `src/vacancy_radar/templates/_report.html`: renders `report.score`,
      `report.flags` (label/severity/reason), `report.gaps`, and `report.similar`
      (company/position/outcome/is_duplicate) — depends on T007
- [x] T014 [US1] Add `GET /` (returns `templates.TemplateResponse("index.html", ...)`) and
      `POST /ui/analyze` (`jd_text: str = Form(...)`, calls `run_analysis()`, returns
      `templates.TemplateResponse("_report.html", {"report": ...})` on success) routes in
      `src/vacancy_radar/api.py` — depends on T007, T012, T013

**Checkpoint**: User Story 1 is fully functional and independently testable — the happy-path
report renders end-to-end (error/empty-state polish comes from User Story 3).

---

## Phase 4: User Story 2 - Trust and reuse the draft paragraph (Priority: P2)

**Goal**: The draft paragraph renders as sentences each visibly paired with their citation, and
a copy action puts the paragraph's exact text on the clipboard.

**Independent Test**: Submit a posting that produces a non-empty draft paragraph; confirm each
citation is visibly tied to its sentence, and confirm the copy action's target contains exactly
the paragraph text.

### Tests for User Story 2

- [x] T015 [P] [US2] Test the rendered `_report.html` HTML pairs each `draft_sentences[].text`
      with its `citation.quote`/`citation.source_id` inside the same rendered element (not two
      disconnected lists), in `tests/test_ui.py`
- [x] T016 [P] [US2] Test the copy control's target text content exactly equals
      `" ".join(d.text for d in report.draft_sentences)` (i.e. `report.draft_paragraph`), in
      `tests/test_ui.py`

### Implementation for User Story 2

- [x] T017 [US2] Extend `_report.html` to iterate `report.draft_sentences` (instead of the flat
      `draft_paragraph`), rendering each sentence's text immediately followed by a visible
      citation marker for its `citation` — depends on T013, T006
- [x] T018 [US2] Add a copy control next to the draft paragraph in `_report.html`, plus a small
      hand-written `src/vacancy_radar/static/ui.js` (no build step, served at `/static/ui.js`)
      using `navigator.clipboard.writeText()` against the full paragraph text — depends on T017

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 - Understand failures without reading logs (Priority: P3)

**Goal**: Empty input, backend failures, and a cold-start empty report all render clear,
plain-language messages; a loading indicator and disabled submit prevent duplicate requests.

**Independent Test**: Submit empty/whitespace input and confirm a validation message appears
with no request sent; separately, submit valid input while the backend is unreachable and
confirm a plain-language failure message appears instead of a blank state or raw error.

### Tests for User Story 3

- [x] T019 [P] [US3] Test `POST /ui/analyze` with empty/whitespace `jd_text` returns `200` HTML
      with a validation message, asserting the fake `LLMProvider`'s `analyze()` was never called,
      in `tests/test_ui.py`
- [x] T020 [P] [US3] Test `POST /ui/analyze` returns `200` HTML with a plain-language
      backend-unavailable message (not the raw exception string) when the fake `LLMProvider`
      raises `LLMProviderError`, in `tests/test_ui.py`
- [x] T021 [P] [US3] Test `POST /ui/analyze` against an empty index (no ingested bullets, no
      citations) renders a clear "nothing to show yet" message rather than empty-looking
      sections, in `tests/test_ui.py`

### Implementation for User Story 3

- [x] T022 [US3] Create `src/vacancy_radar/templates/_error.html`: renders a single `message`
      context variable — depends on T004
- [x] T023 [US3] Wire the empty-input branch (no call to `run_analysis()`, renders `_error.html`
      with a validation message) and the backend-failure branch (catches
      `LLMProviderError`/`ValidationError`/`json.JSONDecodeError` from `run_analysis()`, renders
      `_error.html` with a plain-language message) into `POST /ui/analyze` in
      `src/vacancy_radar/api.py` — depends on T014, T022
- [x] T024 [US3] Add the "nothing to show yet" fallback branch to `_report.html`, shown when
      `flags`, `citations`, and `draft_paragraph` are all empty — depends on T013
- [x] T025 [US3] Add an `hx-indicator` loading element and `hx-disabled-elt` on the submit
      button in `index.html`'s form, so the control is disabled and a visible indicator shown
      while a request is in flight — depends on T012

**Checkpoint**: All three user stories are independently functional — the UI renders a full
report, makes its grounding visible and reusable, and fails clearly when it can't produce one.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final gates required by the constitution before this feature is done.

- [x] T026 [P] Run `ruff check .` and fix any lint findings across all new/changed files
      (Constitution V)
- [x] T027 [P] Run `pytest` and confirm all tests — including the new `tests/test_ui.py`, the
      extended `tests/test_grounding.py`/`tests/test_api.py`, and every existing test from
      [[001-ingestion-cli]]/[[002-similar-retrieval]]/[[003-analyze-report-generation]]/
      [[004-eval-harness]] — pass (Constitution V)
- [x] T028 Manually run every scenario in [quickstart.md](./quickstart.md) in a real browser
      against a running server, `data/example/`, and a real configured LLM backend — the
      automated suite fakes the LLM entirely, so this is the only pass that exercises the actual
      rendered page, the copy action, and the loading/error states end-to-end
- [x] T029 [P] Update the README.md roadmap checkbox: mark "Minimal UI" as done

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup; BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1 has no dependency on US2/US3 and delivers the core "paste and see a report" loop
  - US2 depends on US1's `_report.html`/routes existing — it upgrades the draft-paragraph
    rendering already produced by US1
  - US3 depends on US1's routes existing — it adds the error/empty/loading branches around the
    happy path US1 built
  - Implement in priority order: US1 → US2 → US3
- **Polish (Phase 6)**: Depends on all three user stories being complete

### Within Each User Story

- Tests are written first and must fail before implementation begins
- Foundational data/function changes (T005-T007) before any story-specific route/template work
- Story complete and checkpoint-validated before moving to the next priority

### Parallel Opportunities

- T002, T003 in Setup can run in parallel; T004 depends on all of T001-T003
- T005 in Foundational has no same-file conflict with T007, but T006 depends on T005 and T007
  depends on T006 — this phase is mostly sequential (small, tightly coupled changes)
- Within each user story, the test tasks marked [P] can run in parallel with each other
- T026/T027/T029 in Polish can run in parallel; T028 should run after them (it exercises the
  finished feature)

---

## Parallel Example: Phase 1 + Phase 3 tests

```bash
# Setup (Phase 1) — independent files:
Task: "Create src/vacancy_radar/templates/ and src/vacancy_radar/static/ directories"
Task: "Vendor htmx into src/vacancy_radar/static/htmx.min.js"

# User Story 1 tests — all parallel:
Task: "Test grounding.enforce() populates draft_sentences, in tests/test_grounding.py"
Task: "Test GET / renders the paste-JD form, in tests/test_ui.py"
Task: "Test POST /ui/analyze renders the full report, in tests/test_ui.py"
Task: "Test POST /analyze's JSON response includes draft_sentences, in tests/test_api.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenario 1 (paste and see the full report) and
   Scenario 8 (confirm the JSON contract is unaffected)
5. The core "paste a posting, see a match report" loop is now usable without `curl`

### Incremental Delivery

1. Setup + Foundational → shared data shape and analysis function ready
2. Add US1 → validate independently (quickstart Scenarios 1, 8) → this is the MVP
3. Add US2 → validate independently (quickstart Scenarios 2, 3)
4. Add US3 → validate independently (quickstart Scenarios 4, 5, 6, 7)
5. Phase 6 polish → full quickstart.md pass in a real browser, lint/test gates green

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- No new frontend framework or build toolchain — `jinja2` and `python-multipart` are the only
  new dependencies, both required unconditionally by FastAPI to serve/parse HTML forms at all
  (research.md), and htmx is vendored as a single unbuilt file
- `run_analysis()` (Foundational) is the single place the retrieval → prompt → LLM → grounding
  pipeline is implemented — both `/analyze` and `/ui/analyze` call it; nothing about grounding
  enforcement is duplicated or re-implemented for the UI
- Commit after each task or logical group
- Stop at any checkpoint to validate a story independently
