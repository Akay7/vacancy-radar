## ADDED Requirements

### Requirement: A keyword hit's snippet contains the matched term
`extract_snippet` SHALL, when given text containing a literal
(case-insensitive) occurrence of a query term, return a window of that
text containing the matched term.

#### Scenario: the snippet contains the literal matched term
- **GIVEN** a document's text containing a literal occurrence of a query
  term, and that term
- **WHEN** `extract_snippet` is called with the document's text and the
  query
- **THEN** the returned snippet contains that term (case-insensitive)

### Requirement: A semantic-only hit's snippet falls back to the document's opening
`extract_snippet` SHALL, when no literal query term match exists in the
text (a semantic-only hit, or a keyword hit matched only via FTS
stemming), return the document's opening text instead.

#### Scenario: no literal match falls back to the opening
- **GIVEN** a document's text with no literal occurrence of any query
  term
- **WHEN** `extract_snippet` is called with that text and query
- **THEN** the returned snippet equals the text's opening, bounded to the
  configured maximum length

### Requirement: Snippets are bounded in length and never split a UTF-8 character
`extract_snippet` SHALL return a string no longer than a configured
maximum length, and SHALL NOT split a multi-byte UTF-8 character at
either boundary of the returned window.

#### Scenario: a snippet from multi-byte text stays within bounds and valid
- **GIVEN** a document's text containing multi-byte UTF-8 characters
  (e.g. Cyrillic or emoji) positioned at or near where a snippet window
  boundary would otherwise fall
- **WHEN** `extract_snippet` is called with that text
- **THEN** the returned snippet is no longer than the configured maximum
  length
- **THEN** the returned snippet encodes to UTF-8 without error and
  contains no partial character

### Requirement: extract_snippet is deterministic
`extract_snippet` called twice with the same text and query SHALL return
the same result both times.

#### Scenario: repeated calls return identical snippets
- **GIVEN** a fixed text and query
- **WHEN** `extract_snippet` is called twice with the same arguments
- **THEN** both calls return the identical string

### Requirement: Snippet extraction never affects hit ranking
`search`'s snippet extraction SHALL run only after fusion and ordering
are finalized, and SHALL have no effect on which hits are returned or in
what order.

#### Scenario: hit order is identical whether or not snippets are inspected
- **GIVEN** a query returning multiple hits
- **WHEN** the hits' `doc_id` order is compared against the same query's
  hits with `snippet` values ignored entirely
- **THEN** the order is identical either way
