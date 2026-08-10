## ADDED Requirements

### Requirement: add rejects non-UTF-8 file content with a typed CLI error
The `add` CLI command SHALL, when `--file` names a file that is not
valid UTF-8 text, exit non-zero with a message naming the file and
stating it is not valid text, and SHALL NOT allow an unhandled
exception to propagate out of the command.

#### Scenario: add --file with a PDF exits cleanly, not with a traceback
- **GIVEN** a valid PDF file
- **WHEN** `vacancy-radar add <vacancy> --kind posting --title T --date
  2026-01-01 --file <the PDF's path>` is run
- **THEN** the command exits non-zero, its output names the file and
  states it is not valid text, and no Python traceback appears in its
  output

#### Scenario: the error message names the PDF-attachment workaround
- **WHEN** `add --file` is run against a non-UTF-8 file
- **THEN** the command's error output mentions copying the file into
  the vacancy's `documents/` directory and running `reindex
  --extract-sidecars`

### Requirement: add rejects non-UTF-8 stdin content with the same typed error
The `add` CLI command SHALL, when `--stdin` is given and standard input
does not decode as UTF-8 text, exit non-zero with the same kind of
message `--file` produces for non-UTF-8 content, and SHALL NOT allow an
unhandled exception to propagate out of the command.

#### Scenario: add --stdin with binary input exits cleanly, not with a traceback
- **GIVEN** binary (non-UTF-8) bytes available to pipe as standard
  input
- **WHEN** `vacancy-radar add <vacancy> --kind posting --title T --date
  2026-01-01 --stdin` is run with those bytes piped in
- **THEN** the command exits non-zero, its output states the input is
  not valid text, and no Python traceback appears in its output

### Requirement: add's existing text-content behavior is unaffected by the non-UTF-8 check
`add --file`/`--stdin` SHALL continue to file valid UTF-8 text content
exactly as before this change, for both the default and `--json`
output paths.

#### Scenario: valid UTF-8 --file content is filed unchanged
- **GIVEN** a UTF-8 text file
- **WHEN** `add --file` is run with that file
- **THEN** the command exits 0 and the filed document's content
  matches the file's content, exactly as before this change
