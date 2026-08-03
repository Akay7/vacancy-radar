# Feature Specification: Minimal UI

**Feature Branch**: `005-minimal-ui`

**Created**: 2026-08-03

**Status**: Draft

**Input**: User description: "Make UI, propose framework that could be used."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Paste a posting, see the full match report (Priority: P1)

As a job seeker using this tool, I want to paste a job posting's text into a single screen and
see my match report — score, red/green flags with reasons, gaps, similar past vacancies with
their outcomes, and a draft opening paragraph — without needing to construct an API request by
hand, so the tool is actually usable day-to-day instead of only reachable via `curl`.

**Why this priority**: This is the entire value proposition stated in the README's opening
line. Every other UI concern is secondary to making this one loop usable without a terminal.

**Independent Test**: With the backend running and `data/example/` (or the user's own data)
ingested, open the UI, paste a job posting's text, submit it, and confirm the full report
renders — score, flags, gaps, similar vacancies, and draft paragraph — matching what a direct
`POST /analyze` call with the same text would return.

**Acceptance Scenarios**:

1. **Given** the UI is open and the backend has ingested data, **When** the user pastes job
   posting text and submits it, **Then** the match band, every flag (with its reason), and
   every gap are displayed.
2. **Given** a submitted posting that resembles a previously-ingested vacancy, **When** the
   report renders, **Then** the similar past vacancy is shown together with its outcome and
   whether it's flagged as a likely duplicate.
3. **Given** a submitted posting, **When** the report renders, **Then** the draft opening
   paragraph is displayed as part of the same report.

---

### User Story 2 - Trust and reuse the draft paragraph (Priority: P2)

As a job seeker, I want to see exactly which part of my own experience backs each part of the
draft opening paragraph, and copy that paragraph in one action, so I can both verify it before
using it and drop it straight into a real application without retyping it.

**Why this priority**: The draft paragraph is the single most actionable output of a report,
but Constitution Principle II makes grounding non-negotiable — a user who can't see *why* a
sentence is trustworthy has no way to verify the tool didn't invent it, even though the backend
already enforces this server-side.

**Independent Test**: Submit a posting that produces a non-empty draft paragraph, confirm each
citation backing it is visibly associated with the paragraph (not just returned in the API
response and silently dropped from the screen), and confirm a single action copies the
paragraph's text.

**Acceptance Scenarios**:

1. **Given** a report with a non-empty draft paragraph, **When** the user views it, **Then**
   the citations backing it are visible alongside it, not just present in raw data the user
   never sees.
2. **Given** a rendered draft paragraph, **When** the user triggers the copy action, **Then**
   the exact paragraph text is available to paste elsewhere.

---

### User Story 3 - Understand failures without reading logs (Priority: P3)

As a job seeker, I want a clear, plain-language message when my submission can't be processed
— empty input, or the backend/LLM unavailable — so I know what happened and what to do next,
instead of seeing a blank screen or a raw error.

**Why this priority**: Necessary for a trustworthy tool, but only matters once the core loop
(User Story 1) already works — it hardens an existing flow rather than adding a new one.

**Independent Test**: Submit empty/whitespace-only input and confirm a clear validation message
appears without a request being sent; separately, submit valid input while the backend is
unreachable or misconfigured and confirm a clear, non-technical error message appears.

**Acceptance Scenarios**:

1. **Given** the input field is empty or whitespace-only, **When** the user attempts to
   submit, **Then** a clear message explains that a job posting is required, with no request
   sent.
2. **Given** the backend rejects the request or the LLM backend is unreachable, **When** the
   response comes back, **Then** the UI shows a plain-language explanation, not a raw
   stack trace or unhandled blank state.

---

### Edge Cases

- What happens while an analysis is in progress (LLM latency of several seconds or more)? A
  clear loading/in-progress indicator is shown; the submit action is disabled or debounced so a
  second, duplicate request isn't accidentally triggered.
- How does the UI render a report with no flags, no citations, and an empty draft paragraph
  (cold start — nothing ingested yet)? It states plainly that nothing could be matched yet,
  rather than rendering blank sections that look broken.
- What happens with a very long pasted posting? Submission and rendering both still work; the
  input area scrolls rather than breaking the page layout.
- What happens if the user submits the same posting twice in a row? Each submission is treated
  independently and simply re-renders a fresh report (no client-side caching/history
  requirement — see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single screen where a user can paste job-description
  text and submit it for analysis.
- **FR-002**: The system MUST display the match band, every returned flag with its reason, and
  every returned gap for a submitted posting.
- **FR-003**: The system MUST display the draft opening paragraph together with a visible
  association between each part of it and the citation that grounds it, so grounding is
  verifiable from the screen, not only enforced invisibly server-side.
- **FR-004**: The system MUST display similar past vacancies returned alongside the report,
  including each one's company, position, outcome, and whether it's flagged as a likely
  duplicate.
- **FR-005**: The system MUST let the user copy the draft paragraph's text in one action.
- **FR-006**: The system MUST show a clear, visible indicator while a submitted analysis is in
  progress.
- **FR-007**: The system MUST show a clear, plain-language error message — not a raw
  technical error — when submission fails, distinguishing at least "invalid input" from
  "backend/LLM unavailable."
- **FR-008**: The system MUST prevent submission of empty or whitespace-only input before a
  request is even sent.
- **FR-009**: The system MUST clearly state when a report has nothing to show (no flags, no
  citations, empty draft paragraph) rather than rendering empty-looking sections.
- **FR-010**: The system MUST run entirely against the user's own locally-running backend, and
  MUST NOT transmit posting text or report contents to any third-party hosting or analytics
  service (Constitution I, local-first and private by default).

### Key Entities

No new data entities — this feature only presents the `Report` (score, flags, gaps, similar
vacancies, draft paragraph, citations) already defined and returned by `POST /analyze`
([[003-analyze-report-generation]]).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from pasting a job posting to reading a complete match report in
  one continuous interaction, without constructing an HTTP request or reading raw JSON.
- **SC-002**: Every sentence of a rendered draft paragraph has its supporting citation visibly
  reachable from the same screen.
- **SC-003**: A user who submits invalid input or hits a backend failure can state what went
  wrong from the on-screen message alone, without checking server logs.
- **SC-004**: The UI runs as part of the existing local stack (`docker compose up`) with no new
  external account, hosting service, or paid dependency introduced.

## Assumptions

- Scope is limited to presenting `POST /analyze`'s full report, which already includes the
  `similar` field — a separate standalone screen duplicating `POST /similar` alone is not
  needed.
- Logging or updating a vacancy's outcome is out of scope for this UI: `POST /ingest/vacancy`
  is not implemented yet (still a `501` stub per [[001-ingestion-cli]]'s scope decision) — that
  remains a CLI/file-editing workflow until a future feature implements it.
- This is a single-user, local-only tool: no login, accounts, or multi-user access control are
  in scope.
- No client-side history or persistence of past analyses is required for this feature — each
  submission is a fresh, independent report (YAGNI; can be added later if real usage shows a
  need for it).
- The choice of frontend framework/toolchain is an implementation decision, made in this
  feature's `/speckit-plan` phase against Constitution Principle IV (right-sized infra) — not
  a business requirement fixed by this specification.
