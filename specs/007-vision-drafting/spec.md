# Feature Specification: Vision-Based Image Drafting

**Feature Branch**: `007-vision-drafting`

**Created**: 2026-08-03

**Status**: Draft

**Input**: User description: "Maybe better to use vision llm instead of ocr?" — a follow-up to [[006-vacancy-upload]], raised after that feature's manual validation showed real OCR (`pytesseract`) mangling a company name ("Nimbus Cloud Systems" → "NimbusCloud systems") that a vision-capable model would very likely have read correctly.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accurate drafts from a photo or screenshot (Priority: P1)

As the maintainer, when I upload an image — a photo or screenshot of a job posting — I want the
drafted company, position, and date to come from the LLM actually looking at the image, not
only from OCR'd text, so the draft is accurate even when a photo is imperfectly lit, skewed, or
has formatting OCR struggles with.

**Why this priority**: This is the entire reason the feature exists — a concrete, already-observed
accuracy problem, not a hypothetical one.

**Independent Test**: Upload a real, imperfect photo of a posting through the existing upload
screen ([[006-vacancy-upload]]) and confirm the drafted fields are at least as accurate as, and
typically more accurate than, what OCR-only drafting produced before.

**Acceptance Scenarios**:

1. **Given** the upload screen with a vision-capable backend configured, **When** the maintainer
   uploads a photographed or screenshotted posting, **Then** the drafted company/position/date
   reflect the LLM's own reading of the image, not only OCR'd text.
2. **Given** the same upload, **When** the draft is shown, **Then** the maintainer can still
   review and edit every field before saving — a vision-derived draft is exactly as reviewable
   and correctable as an OCR-derived one, never auto-trusted.

---

### User Story 2 - Clear signal when vision isn't available (Priority: P2)

As the maintainer, if the configured LLM backend can't interpret images directly — for example,
a local model without vision support, or a vision attempt that errors partway through — I want
to be told plainly that image-based drafting didn't work and why, rather than being handed a
vague or silently-empty draft, so I understand the problem and know I need to either fill in
the fields myself or switch to a vision-capable backend/model.

**Why this priority**: Preserves the existing never-block-logging-a-vacancy guarantee from
[[006-vacancy-upload]] (manual entry is always the floor) — necessary, but secondary to the
core accuracy improvement in User Story 1. Local OCR (`pytesseract`) is being removed as part
of this feature, so there is no OCR-based intermediate step left to fall back to — the honest
signal *is* the fallback.

**Independent Test**: Configure a backend/model without vision support, upload an image, and
confirm the maintainer sees a specific message explaining that image-based drafting isn't
available with the current backend — not a generic error, and not a silently empty draft — and
can still fill in every field manually and save.

**Acceptance Scenarios**:

1. **Given** a configured backend/model that cannot interpret images, **When** the maintainer
   uploads an image, **Then** the system shows a specific message explaining that this backend
   can't read images directly, and that every field must be filled in manually.
2. **Given** a vision attempt that errors partway through (e.g., a transient backend failure),
   **When** drafting is attempted, **Then** the maintainer sees the same kind of specific,
   understandable message — not a raw/technical error and not a silent empty draft.
3. **Given** a vision-drafting failure of either kind, **When** the draft screen is shown,
   **Then** the maintainer can still fill in every field manually and save successfully,
   unchanged from [[006-vacancy-upload]]'s existing floor behavior.

---

### Edge Cases

- What happens for PDF and DOCX uploads? Unchanged — this feature is scoped to image uploads
  only; PDF/DOCX keep their existing local text-extraction path (`pypdf`/`python-docx`, neither
  of which is affected by removing OCR).
- What happens when a vision-based attempt itself fails or errors mid-request? The maintainer
  sees the specific "this backend can't read images" message and falls back to manual entry —
  there is no OCR text to fall back to instead.
- What happens to image files already sitting in an existing vacancy folder's `sources/`
  (ingested via the CLI, not uploaded)? They stop contributing any embedded text to `/similar`
  and `/analyze` retrieval (previously OCR'd text, now none) — the vacancy itself remains fully
  discoverable via its `vacancy.yaml` record, only the image's own content is no longer
  full-text-searchable. Existing/CLI ingestion is unaffected in every other respect.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the uploaded document is an image, the system MUST derive draft
  company/position/date by having the configured LLM backend interpret the image directly —
  local OCR is removed as part of this feature, so the image itself is the only source for
  image-upload drafting.
- **FR-002**: If the configured backend/model cannot interpret the image, or the vision attempt
  fails/errors, the system MUST show the maintainer a specific, plain-language message
  explaining that image-based drafting isn't available with the current backend — not a
  generic error and not a silently empty draft.
- **FR-003**: Regardless of why image-based drafting didn't work, the system MUST still let the
  maintainer fill in every field manually and save successfully, exactly as already required
  for any failed draft ([[006-vacancy-upload]] FR-008) — never a hard failure blocking the
  upload.
- **FR-004**: This feature MUST NOT require the maintainer to configure anything new to benefit
  from it — behavior is automatic for whichever backend is already configured; the specific
  message in FR-002 is what tells them when their current configuration doesn't support it.
- **FR-005**: PDF and DOCX uploads MUST continue to use local text extraction exactly as before
  (`pypdf`/`python-docx`, neither of which does OCR) — this feature does not change their
  drafting path.
- **FR-006**: The maintainer MUST still be able to review and edit every drafted field before
  saving, unchanged from [[006-vacancy-upload]] — a vision-derived draft is exactly as
  reviewable/correctable as an OCR-derived one, not auto-trusted.
- **FR-007**: The system MUST NOT send the uploaded image anywhere other than the maintainer's
  own configured LLM backend, consistent with the same local-first/private-by-default boundary
  [[006-vacancy-upload]] already established for extracted text.
- **FR-008**: Local OCR (`pytesseract`) MUST be removed from the project entirely — it is not
  kept as a fallback path for any case (image uploads or otherwise).

### Key Entities

No new entities — this feature changes how `Draft Vacancy Metadata` ([[006-vacancy-upload]]) is
derived for image uploads specifically; the shape of the draft and the resulting `Vacancy
Record` are unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Drafted company/position/date for a representative set of real photographed or
  screenshotted postings are at least as accurate as the old OCR-only approach was, and
  noticeably better for images where OCR previously introduced errors (e.g., the "Nimbus Cloud
  Systems" → "NimbusCloud systems" case observed during [[006-vacancy-upload]]'s own
  validation).
- **SC-002**: Uploading an image while using a backend/model that can't interpret images
  directly always produces a specific, understandable explanation and a working manual-entry
  path — never an unhandled error, and never a silently empty/misleading draft.
- **SC-003**: PDF and DOCX drafting accuracy and behavior are unchanged from before this feature.

## Assumptions

- Scoped to image uploads (PNG/JPEG) only; PDF and DOCX keep their existing local-extraction-only
  path unchanged — a scanned/no-text-layer PDF remains a possible future extension, not part of
  this feature, matching [[006-vacancy-upload]]'s own deliberately scoped-down spirit.
- Constitution Principle III's "same interface" requirement is about calling code never
  special-casing a specific provider — not about both providers using identical internal
  techniques. A vision-capable backend (Claude, or any Ollama model the maintainer has
  configured with vision support) may use it; a backend without vision support surfaces the
  specific message from FR-002 instead — the shared `LLMProvider` interface and the calling
  route stay identical either way, the same way `analyze()` already differs internally between
  providers (structured schema vs. JSON-mode-plus-retry) behind one shared method today.
- Local OCR (`pytesseract`) is removed entirely as part of this feature (FR-008) — the
  maintainer explicitly decided a clear "this doesn't work with your current backend" signal is
  more valuable than a silent, potentially inaccurate intermediate fallback. This also removes
  `pytesseract`/`Pillow` from the project's dependencies and the Dockerfile's `tesseract-ocr`
  system package.
- Exactly how the system determines "this backend/model does or doesn't support vision" (e.g.,
  always attempt vision and treat any failure as "not available", versus some other detection)
  is an implementation decision for the planning phase, not fixed by this specification.
- Removing OCR means image files placed directly in a vacancy folder's `sources/` (the CLI
  ingestion path, not the upload UI) no longer contribute any embedded text to retrieval — this
  is an accepted, minor side effect (see Edge Cases) rather than something this feature
  compensates for (doing so would require calling an LLM from the offline CLI ingestion path,
  a new coupling out of scope here).
