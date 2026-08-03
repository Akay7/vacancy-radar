# Feature Specification: Vacancy Document Upload

**Feature Branch**: `006-vacancy-upload`

**Created**: 2026-08-03

**Status**: Draft

**Input**: User description: "sometimes there's no `vacancy.yaml` file in `.yaml` format. It could be Image or PDF file, or DOCX file. Let's load not only .yaml files into rag" — refined via clarification into a web upload screen that finally implements `POST /ingest/vacancy`, with LLM-drafted metadata the maintainer reviews before saving.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload a posting/offer document instead of hand-authoring YAML (Priority: P1)

As the maintainer, I want to upload a job posting or offer document — an image, PDF, DOCX, or
plain text file — through a web screen and see the company, position, and date automatically
drafted from it, so I can log a new vacancy without hand-authoring a `vacancy.yaml` file or
retyping details already present in the document.

**Why this priority**: This is the entire reason the feature exists — replacing the
previously-only-option (hand-write a structured YAML file yourself) with one that starts from
whatever document you actually have in hand.

**Independent Test**: Upload a real posting document through the new screen and confirm
draft values for company/position/date appear pre-filled with values that plausibly match the
document's actual content.

**Acceptance Scenarios**:

1. **Given** the upload screen is open, **When** the maintainer uploads a PDF of a job posting,
   **Then** draft company/position/date values derived from the posting are shown before
   anything is saved.
2. **Given** the same screen, **When** the maintainer uploads an image (e.g., a screenshot) or
   a DOCX file instead, **Then** the same drafting behavior applies — the accepted format
   doesn't change the flow.

---

### User Story 2 - Review and correct the draft before it's saved (Priority: P2)

As the maintainer, I want to edit any of the drafted fields — and always set the outcome
myself — before confirming, so a misreading by the LLM (wrong company name, wrong date) never
silently creates an incorrect vacancy record.

**Why this priority**: Directly protects the integrity of the vacancy history this whole
project is built around; the drafting in User Story 1 only has value if it's trustworthy, and
trustworthiness here comes from the human checking it, not from the extraction being perfect.

**Independent Test**: Upload a document, deliberately change one of the drafted fields before
confirming, and verify the saved record reflects the edited value, not the original draft.

**Acceptance Scenarios**:

1. **Given** a drafted set of fields, **When** the maintainer edits any field and confirms,
   **Then** the saved vacancy record reflects the edited values.
2. **Given** a drafted set of fields, **When** the maintainer has not yet set an outcome value,
   **Then** the system does not let the record be saved without one — outcome is never
   auto-filled, since a posting/offer document can't reflect a status that hasn't happened yet.
3. **Given** a drafted set of fields the maintainer has not yet confirmed, **When** the
   maintainer leaves the screen without confirming, **Then** no vacancy record is created.

---

### User Story 3 - The uploaded document becomes retrievable immediately (Priority: P3)

As the maintainer, I want the uploaded document's content embedded into the vacancy history
index as soon as I confirm, so `/similar` and `/analyze` immediately reflect this new vacancy
without a separate manual ingestion step.

**Why this priority**: Completes the loop — a vacancy logged through the web screen should be
just as usable as one ingested via the existing CLI, without an extra step the maintainer could
forget to run.

**Independent Test**: Upload and confirm a new vacancy, then immediately submit matching text to
`/similar` and confirm the new vacancy appears in the results.

**Acceptance Scenarios**:

1. **Given** a newly confirmed vacancy, **When** a matching job posting is submitted to
   `/similar` right afterward, **Then** the new vacancy appears among the results without
   running any separate ingestion command.

---

### User Story 4 - Existing folder-based ingestion accepts the same document formats (Priority: P4)

As the maintainer, I want files already sitting in a vacancy folder's `sources/`/
`correspondence/` subdirectories to also support image, PDF, and DOCX (not only markdown/text),
so a vacancy logged by hand on disk works the same way as one logged through the upload screen.

**Why this priority**: Keeps the two ways of logging a vacancy (the existing CLI/folder path and
the new upload screen) consistent with each other — smallest, most self-contained slice, and a
natural reuse of whatever document-reading capability the other stories need anyway.

**Independent Test**: Manually place a PDF into an existing vacancy folder's `sources/`
directory, run the existing sync command, and confirm its text is embedded rather than skipped
or causing an error.

**Acceptance Scenarios**:

1. **Given** a vacancy folder with a PDF, DOCX, or image file under `sources/` or
   `correspondence/`, **When** the folder is ingested via the existing CLI, **Then** that file's
   extracted text is embedded into the vacancy history index the same way a `.md` file already
   is.

---

### Edge Cases

- What happens when the uploaded file's text can't be read at all (a blank scan, a corrupted
  PDF)? The maintainer sees a clear message and can still fill in every field manually — the
  upload doesn't have to be abandoned just because extraction failed.
- What happens when an unsupported file type is uploaded? A clear rejection message, not a
  silent failure or a broken record.
- What happens when the confirmed fields resolve to the same natural key as an
  already-ingested vacancy (same date + company + position)? The maintainer sees this clearly
  before saving, consistent with how the existing folder-based ingestion already reports this
  conflict — it is not silently overwritten.
- What happens when the configured LLM backend is unavailable at draft time? The maintainer can
  still type every field manually and log the vacancy — a failed or unavailable draft step MUST
  NOT block logging a vacancy altogether.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a web screen where the maintainer can upload a single
  document (image, PDF, DOCX, or plain text) representing a job posting or offer.
- **FR-002**: The system MUST derive draft values for company, position, and date from the
  uploaded document's content, for the maintainer to review before anything is saved.
- **FR-003**: The system MUST require the maintainer to set the outcome value themselves — it
  MUST NOT be derived from the uploaded document, since an initial posting/offer document cannot
  reflect an outcome that hasn't happened yet.
- **FR-004**: The system MUST let the maintainer review and edit every drafted field before the
  vacancy record is saved, and MUST NOT save a record that hasn't been explicitly confirmed.
- **FR-005**: Upon confirmation, the system MUST store the uploaded document as part of the new
  vacancy record and embed its extracted text into the searchable vacancy history index
  immediately, without requiring a separate manual ingestion step.
- **FR-006**: The system MUST detect when the confirmed fields resolve to the same natural key
  as an already-ingested vacancy and clearly surface this before saving, consistent with the
  existing conflict-detection behavior for folder-based ingestion.
- **FR-007**: The system MUST reject unsupported file types and unreadable/empty documents with
  a clear message, rather than silently creating an empty or broken vacancy record.
- **FR-008**: The system MUST still let the maintainer manually type or correct every field even
  if the automatic drafting step fails or the configured LLM backend is unavailable — a failed
  draft MUST NOT block logging a vacancy.
- **FR-009**: The system MUST extend the existing folder-based ingestion path to accept image,
  PDF, and DOCX files (not only plain text/markdown) under a vacancy folder's
  `sources/`/`correspondence/` subdirectories, so both ways of logging a vacancy handle the same
  document formats consistently.
- **FR-010**: The system MUST NOT send the uploaded document or its extracted content anywhere
  other than the maintainer's own configured LLM backend and local vector store — consistent
  with the project running entirely on the maintainer's own machine against their own data.

### Key Entities

- **Uploaded Document**: The raw file the maintainer uploads (image, PDF, DOCX, or text), its
  extracted text content, and its eventual place within the created vacancy record.
- **Draft Vacancy Metadata**: The proposed company/position/date values plus the
  maintainer-provided outcome, pending confirmation — not yet a saved vacancy record until
  confirmed.
- **Vacancy Record** *(existing, reused from [[001-ingestion-cli]])*: company, position, date,
  outcome, and the natural key derived from them. This feature is a new way to produce one, not
  a new shape of it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can go from having only a posting/offer document to a fully logged,
  retrievable vacancy record in one continuous web session, without editing any file on disk
  directly.
- **SC-002**: No vacancy record is ever saved without the maintainer having seen and had the
  chance to correct every field, including when the draft is wrong.
- **SC-003**: A vacancy logged through the upload screen is immediately reflected in `/similar`
  and `/analyze` results, with no separate ingestion step required.
- **SC-004**: An unsupported file, an unreadable document, or a natural-key conflict is clearly
  reported in every case tested — never silently ignored or resulting in a broken record.
- **SC-005**: A vacancy folder containing an image, PDF, or DOCX file under `sources/` or
  `correspondence/` ingests successfully via the existing CLI, with that file's content
  searchable afterward exactly as a `.md` file's already is.

## Assumptions

- Company, position, and date are the fields drafted from the uploaded document; outcome is
  always set by the maintainer, since it reflects a real-world status an initial posting/offer
  document cannot contain.
- One document per upload is in scope for this feature — batch/multi-file upload is out of
  scope, matching the minimal, single-purpose spirit of the rest of the UI; it can be extended
  later if real usage shows a need for it.
- The existing CLI/folder-based ingestion path remains fully supported and unchanged for
  bulk/history ingestion — this feature adds a second, additional way to log a single new
  vacancy; it does not replace or deprecate the first.
- Exact document size/page limits, and which specific local libraries or LLM vision capability
  perform text extraction, are implementation decisions for the planning phase, not fixed by
  this specification.
- The human-review step at confirmation time is this feature's safeguard against incorrect
  drafted metadata — in the same spirit as the project's broader rule against trusting
  unverified LLM output, but implemented as a review step rather than an automated citation
  check like `grounding.enforce()`, since the drafted values here are a handful of short factual
  fields a human can quickly verify against the uploaded document directly, unlike a longer
  generated narrative.
