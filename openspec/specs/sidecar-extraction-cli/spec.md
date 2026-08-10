# sidecar-extraction-cli Specification

## Purpose
Wires the CLI's `reindex` command to stage 3's already-implemented PDF
sidecar extraction (`extract_sidecars`), which existed but had no
reachable entry point before this capability: `reindex
--extract-sidecars` triggers it, and `reindex`'s plain-text output
surfaces whatever warnings the resulting `IndexReport` carries instead
of dropping them.

## Requirements

### Requirement: reindex --extract-sidecars triggers PDF sidecar extraction
The `reindex` CLI command SHALL, when called with `--extract-sidecars`,
pass `extract_sidecars=True` to `core.reindex`. Without the flag, it
SHALL pass `extract_sidecars=False` (or omit it), matching this
command's behavior before the flag existed.

#### Scenario: --extract-sidecars creates a sidecar for an eligible PDF
- **GIVEN** a vault with a valid, text-bearing PDF filed under a
  vacancy's `documents/` directory, and no existing sidecar for it
- **WHEN** `vacancy-radar reindex --extract-sidecars` is run
- **THEN** the command exits 0 and a `.pdf.md` sidecar now exists on
  disk for that PDF

#### Scenario: reindex with no flag creates no sidecar
- **GIVEN** the same vault as above, with no existing sidecar for its
  PDF
- **WHEN** `vacancy-radar reindex` is run with no `--extract-sidecars`
- **THEN** the command exits 0 and no sidecar is created for that PDF

### Requirement: reindex's plain-text output prints every warning IndexReport carries
The `reindex` CLI command's plain-text (non-`--json`) output SHALL
include every warning present in the `IndexReport` its underlying
`core.reindex` call returns, regardless of warning kind.

#### Scenario: an extraction warning appears in plain-text output
- **GIVEN** a vault with a malformed `.pdf` file under a vacancy's
  `documents/` directory
- **WHEN** `vacancy-radar reindex --extract-sidecars` is run without
  `--json`
- **THEN** the command's output includes text naming that file as a
  warning

#### Scenario: a non-extraction warning also appears in plain-text output
- **GIVEN** a vault whose `IndexReport` carries a warning of a kind
  unrelated to PDF extraction (e.g. `vanished_source`)
- **WHEN** `vacancy-radar reindex` is run without `--json`
- **THEN** the command's output includes that warning's message

### Requirement: reindex --json's warnings field is unaffected
`vacancy-radar reindex --json`'s output SHALL continue to include a
`warnings` field carrying the same data as `IndexReport.warnings`,
serialized, exactly as it did before this change.

#### Scenario: --json output still includes the warnings field
- **WHEN** `vacancy-radar reindex --json` is run
- **THEN** the parsed JSON output has a `warnings` key whose value is a
  list, populated with any warnings the call produced
