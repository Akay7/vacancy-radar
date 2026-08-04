# Feature Specification: Clear Navigation & Visual Polish for Ingest Flow

**Feature Branch**: `008-ingest-flow-clarity`

**Created**: 2026-08-04

**Status**: Draft

**Input**: User description: "ux\ui is very ugly, it's not clear what user should doing. There should be the clear path of how to ingest new vacancy."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover how to log a vacancy from the home screen (Priority: P1)

A user opens Vacancy Radar for the first time (or returns after a while) and lands on the paste-a-posting screen. Without already knowing the app has a second screen for logging vacancy history, they need to discover it and get there in one click.

**Why this priority**: Today the "log a vacancy" screen exists only at a URL the user must already know. This is the core complaint — the app has a feature with no visible path to it. Nothing else in this spec matters if this gap isn't closed.

**Independent Test**: Load the home screen with no prior knowledge of the app; confirm a visible, labeled link/button reaches the log-a-vacancy screen without typing a URL.

**Acceptance Scenarios**:

1. **Given** a user is on the home (analyze) screen, **When** they look at the page, **Then** they see a clearly labeled way to get to "log a vacancy" without scrolling past unrelated content.
2. **Given** a user is on the log-a-vacancy screen, **When** they want to go back to analyzing a posting, **Then** they see a clearly labeled way back, without relying on the browser's back button.

---

### User Story 2 - Understand what step they're on while logging a vacancy (Priority: P2)

A user uploads a posting/offer document to log a vacancy. The flow has three steps (upload → review drafted fields → confirm), but nothing on screen currently signals which step is active, whether the draft succeeded, or what happens next.

**Why this priority**: Once the user can find the flow (P1), the next-biggest source of confusion is inside it — a bare form with results appended below it gives no sense of progress or state.

**Independent Test**: Walk through uploading a file and confirming a draft; at each stage, confirm the screen indicates the current step and clearly separates it from the previous step's content.

**Acceptance Scenarios**:

1. **Given** a user has just uploaded a file, **When** drafting is in progress, **Then** the screen shows a distinct loading/in-progress state rather than an unchanged form.
2. **Given** drafting succeeds, **When** the draft appears, **Then** it is visually distinguished as "step 2 of 2: review" rather than plain text appended below the upload form.
3. **Given** drafting fails (e.g., the configured backend can't read the file), **When** the error appears, **Then** it is visually distinguished as an error (not styled the same as normal content) and states what the user can still do (fill in fields by hand).

---

### User Story 3 - Recognize the app as one coherent tool, not two disconnected pages (Priority: P3)

A user moving between the analyze screen and the log-a-vacancy screen currently sees two pages with different structure, spacing, and no shared visual identity — as if they were different applications.

**Why this priority**: Lower priority than navigation and in-flow clarity (P1/P2), but "very ugly" and inconsistent styling was named directly in the request — a shared, deliberate visual style closes that gap.

**Independent Test**: Compare both screens side by side; confirm shared layout structure, typography, spacing, and button/error styling.

**Acceptance Scenarios**:

1. **Given** a user visits both screens in the same session, **When** they compare them, **Then** headings, buttons, spacing, and error styling look like they belong to the same application.

---

### Edge Cases

- What happens when a user is deep in the review step of logging a vacancy and clicks the nav link back to the home screen? (Answer: normal navigation; no unsaved-state warning is required since nothing is persisted until "confirm" is clicked, but the transition should not feel like a dead end.)
- How does the navigation element behave on a narrow (mobile-width) browser window? It must remain visible and usable, not disappear or overlap content.
- What does a user with no vacancy history yet see, and does that state hint at the ingest flow?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The home (analyze) screen MUST display a clearly labeled, always-visible link or button to the log-a-vacancy screen.
- **FR-002**: The log-a-vacancy screen MUST display a clearly labeled, always-visible link or button back to the home (analyze) screen.
- **FR-003**: The log-a-vacancy flow MUST visually indicate which of its steps (upload, review draft, confirmed) is currently active.
- **FR-004**: The log-a-vacancy flow MUST visually distinguish an in-progress (loading) state from both the initial upload state and the completed-draft state.
- **FR-005**: Error states (e.g., a failed draft attempt) MUST be visually distinguished from normal content (e.g., a distinct color/icon/labeling treatment) rather than appearing as plain, unstyled text.
- **FR-006**: The home screen and the log-a-vacancy screen MUST share a consistent visual style — typography, color palette, spacing, and button appearance — so both read as the same application.
- **FR-007**: The home screen MUST state, in plain language, what each of the two primary actions (analyze a posting vs. log a vacancy) is for, so a user can pick the right one without trial and error.
- **FR-008**: Navigation elements MUST remain visible and usable at common mobile browser widths (down to 375px).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user with no prior knowledge of the app can find and open the log-a-vacancy screen from the home screen in under 10 seconds.
- **SC-002**: Every screen in the app provides a working path to every other primary screen without the user typing a URL or using browser back/forward.
- **SC-003**: A user can correctly state which step of the log-a-vacancy flow they are on (upload / review / done) just by looking at the screen, without reading surrounding instructions.
- **SC-004**: A user attempting to upload an unsupported or failing file can tell, within one glance, that something went wrong and what to do next.

## Assumptions

- No new backend behavior is required — `/analyze`, `/ui/analyze`, `/ui/ingest/draft`, and `/ui/ingest/confirm` keep their existing request/response contracts. This feature is about navigation, layout, and visual/state feedback around the existing flows.
- The app continues to be rendered server-side with page reloads/partial swaps for interactivity (its existing approach) — this feature does not require introducing a client-side framework or a build step.
- Primary usage remains desktop browser, single user, single tab at a time; mobile support only needs to reach "usable," not be the primary design target (per FR-008's 375px floor).
- "Visually distinguished" states (loading, error, step progress) can be achieved with color, iconography, and layout alone — no new libraries beyond what the project already serves are assumed necessary.
