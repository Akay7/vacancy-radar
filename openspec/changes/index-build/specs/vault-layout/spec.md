## ADDED Requirements

### Requirement: sidecar_path_for expresses the sidecar naming convention
`sidecar_path_for(source_path)` SHALL return the path of the sidecar
that would shadow `source_path`: `source_path`'s own name with `.md`
appended (not its stem — the full filename, extension included).

#### Scenario: sidecar path is the source's full filename plus .md
- **GIVEN** a source path ending in `spec.pdf`
- **WHEN** `sidecar_path_for` is called with that path
- **THEN** it returns a path in the same directory named `spec.pdf.md`

#### Scenario: distinct sources with the same stem get distinct sidecar paths
- **GIVEN** two source paths in the same directory, `notes.pdf` and
  `notes.docx`
- **WHEN** `sidecar_path_for` is called with each
- **THEN** it returns `notes.pdf.md` and `notes.docx.md` respectively —
  two distinct paths, neither a prefix collision with the other's
  source
