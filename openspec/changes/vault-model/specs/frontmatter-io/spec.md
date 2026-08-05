## ADDED Requirements

### Requirement: Frontmatter round-trips byte-identically
The system SHALL reproduce a markdown file's original text byte for
byte, including frontmatter key order and body whitespace, when the
file is parsed and the resulting metadata and body are serialized back.

#### Scenario: parse then serialize reproduces the original text
- **GIVEN** a markdown file with YAML frontmatter and a body
- **WHEN** the file's text is parsed with `parse` and the resulting
  metadata and body are passed to `serialize`
- **THEN** the serialized output equals the original text byte for byte

### Requirement: Missing frontmatter delimiter is rejected
`parse` SHALL raise `MissingFrontmatterError` when the input text does
not begin with a frontmatter delimiter.

#### Scenario: text with no frontmatter delimiter
- **GIVEN** text that does not start with a `---` frontmatter delimiter
- **WHEN** `parse` is called on that text
- **THEN** `MissingFrontmatterError` is raised

### Requirement: Malformed YAML is rejected with the file identified
`parse` SHALL raise `MalformedFrontmatterError` naming the file when the
frontmatter block contains YAML that cannot be parsed.

#### Scenario: unparseable YAML in the frontmatter block
- **GIVEN** text whose frontmatter block is not valid YAML
- **WHEN** `parse` is called on that text with a file identifier
- **THEN** `MalformedFrontmatterError` is raised
- **THEN** the error identifies the file the malformed YAML came from

### Requirement: A body line of `---` is not a delimiter
`parse` SHALL treat only the frontmatter's own opening and closing
delimiters as delimiters — a `---` line inside the body SHALL be part
of the body text, not treated as starting a new frontmatter block.

#### Scenario: body contains a --- line
- **GIVEN** a markdown file whose body contains a line consisting only
  of `---`
- **WHEN** the file's text is parsed with `parse`
- **THEN** the body returned includes that `---` line as ordinary body
  text
- **THEN** parsing and re-serializing the file reproduces the original
  text byte for byte
