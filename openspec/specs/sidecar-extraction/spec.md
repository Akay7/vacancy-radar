# sidecar-extraction Specification

## Purpose
TBD - created by openspec-sync-specs during change index-build. Update Purpose after archive.

## Requirements

### Requirement: Extraction eligibility is PDF-only, by extension
`extract_to_sidecar` SHALL attempt extraction only for a source path
with a `.pdf` suffix. For any other extension, it SHALL take no action
and SHALL NOT write a sidecar.

#### Scenario: a .py file gets no sidecar and no extraction attempt
- **GIVEN** a source file `solution.py` under a vacancy's `documents/`
  directory
- **WHEN** `extract_to_sidecar` is called with that path
- **THEN** no sidecar file is written
- **THEN** it returns `None`

#### Scenario: a .zip file gets no sidecar and no extraction attempt
- **GIVEN** a source file `submission.zip` under a vacancy's
  `documents/` directory
- **WHEN** `extract_to_sidecar` is called with that path
- **THEN** no sidecar file is written
- **THEN** it returns `None`

### Requirement: A valid PDF's text is extracted into a sidecar
`extract_to_sidecar` SHALL, for a valid, unencrypted PDF yielding at
least 200 characters of text, write a sidecar containing that text and
frontmatter naming the source, the source's hash, the extractor
identity, and the extraction time, with `manually_corrected: false`.

#### Scenario: extracting a valid PDF writes a sidecar with text
- **GIVEN** a valid, unencrypted, text-bearing PDF at `spec.pdf`
- **WHEN** `extract_to_sidecar` is called with that path
- **THEN** it returns the path to `spec.pdf.md`
- **THEN** the sidecar's frontmatter has `extracted_from: spec.pdf`, a
  `source_hash` matching the PDF's content hash, an `extractor` value,
  an `extracted_at` date, and `manually_corrected: false`
- **THEN** the sidecar's body is non-empty text drawn from the PDF

### Requirement: Regeneration is gated on source_hash, not re-run unconditionally
`extract_to_sidecar` SHALL be a no-op (no write) when a sidecar already
exists with a `source_hash` matching the current source file's content
hash. When the source's content hash no longer matches the sidecar's
recorded `source_hash`, it SHALL regenerate the sidecar — unless the
existing sidecar has `manually_corrected: true`, in which case it SHALL
NOT regenerate and SHALL instead report a stale-sidecar warning.

#### Scenario: re-extracting with an unchanged source_hash is a no-op
- **GIVEN** a sidecar already extracted from its current source, with a
  matching `source_hash`
- **WHEN** `extract_to_sidecar` is called again with the same source
- **THEN** the sidecar file is not rewritten (its content is unchanged,
  byte for byte)

#### Scenario: a changed source_hash regenerates the sidecar
- **GIVEN** a sidecar whose `source_hash` no longer matches its
  source's current content hash
- **WHEN** `extract_to_sidecar` is called with that source
- **THEN** the sidecar is rewritten with a `source_hash` matching the
  source's current content hash

#### Scenario: manually_corrected sidecars are never regenerated
- **GIVEN** a sidecar with `manually_corrected: true` and a
  `source_hash` that no longer matches its source's current content
  hash
- **WHEN** `extract_to_sidecar` is called with that source
- **THEN** the sidecar file is not rewritten
- **THEN** a stale-sidecar warning is reported, naming the sidecar

### Requirement: Extraction failures write an empty sidecar and a warning, never raise
`extract_to_sidecar` SHALL, for an encrypted PDF, a malformed PDF, or a
PDF yielding under 200 characters of text (including a scanned PDF
with no text layer), write a sidecar with an empty body and report a
warning naming the cause — and SHALL NOT raise an exception in any of
these cases.

#### Scenario: an encrypted PDF writes an empty sidecar plus a warning
- **GIVEN** a password-encrypted PDF
- **WHEN** `extract_to_sidecar` is called with that path
- **THEN** it writes a sidecar with an empty body
- **THEN** it reports a warning naming the source and the reason
- **THEN** it does not raise

#### Scenario: a malformed PDF writes an empty sidecar plus a warning
- **GIVEN** a file with a `.pdf` extension whose bytes are not a valid
  PDF structure
- **WHEN** `extract_to_sidecar` is called with that path
- **THEN** it writes a sidecar with an empty body
- **THEN** it reports a warning naming the source and the reason
- **THEN** it does not raise

#### Scenario: a scanned PDF with no text layer writes an empty sidecar
- **GIVEN** a valid, unencrypted PDF containing only an image, with no
  extractable text layer
- **WHEN** `extract_to_sidecar` is called with that path
- **THEN** it writes a sidecar with an empty body
- **THEN** it reports a warning naming the source

#### Scenario: a hand-corrected scanned-PDF sidecar indexes normally afterward
- **GIVEN** the empty sidecar written for a scanned PDF, subsequently
  hand-edited to add body text and set `manually_corrected: true`
- **WHEN** `extract_to_sidecar` is called again with the same source
  (content hash unchanged)
- **THEN** the hand-edited sidecar is left untouched (matches the
  no-op and never-regenerate-when-corrected rules above)

### Requirement: Extraction warnings are returned, never printed
`extract_to_sidecar` SHALL communicate every failure as a returned or
collected warning value. It SHALL NOT write to stdout or stderr.

#### Scenario: no output on stdout or stderr during a failing extraction
- **GIVEN** an encrypted, a malformed, and a scanned PDF
- **WHEN** `extract_to_sidecar` is called with each, with stdout and
  stderr captured
- **THEN** nothing is written to either stream
</content>
