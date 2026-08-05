## ADDED Requirements

### Requirement: recall_at_k measures the fraction of expected documents present in the top k retrieved
`recall_at_k(expected, retrieved, k)` SHALL return the fraction of
`expected`'s document ids present among `retrieved`'s first `k`
entries, as a float in `[0.0, 1.0]`.

#### Scenario: a single expected document ranking first scores 1.0
- **GIVEN** `expected` containing exactly one document id
- **AND** `retrieved` with that document id as its first entry
- **WHEN** `recall_at_k(expected, retrieved, k=5)` is called
- **THEN** the result is `1.0`

#### Scenario: an expected document absent from the top k scores 0.0
- **GIVEN** `expected` containing exactly one document id
- **AND** `retrieved` whose first five entries do not include that id
- **WHEN** `recall_at_k(expected, retrieved, k=5)` is called
- **THEN** the result is `0.0`

#### Scenario: partial recall with three expected and two found in the top five
- **GIVEN** `expected` containing exactly three document ids
- **AND** `retrieved` whose first five entries include exactly two of
  those three ids
- **WHEN** `recall_at_k(expected, retrieved, k=5)` is called
- **THEN** the result is `2/3`

### Requirement: mrr measures the reciprocal rank of the first expected hit
`mrr(expected, retrieved)` SHALL return `1 / rank` where `rank` is the
1-based position in `retrieved` of the first entry whose id appears in
`expected`, or `0.0` if no entry of `retrieved` appears in `expected`.

#### Scenario: mrr reflects the rank of the first expected hit
- **GIVEN** `expected` containing a document id that appears at the
  third position of `retrieved`, with no expected id at an earlier
  position
- **WHEN** `mrr(expected, retrieved)` is called
- **THEN** the result is `1/3`

#### Scenario: no expected document present in retrieved scores 0.0
- **GIVEN** `expected` containing at least one document id
- **AND** `retrieved` containing none of `expected`'s ids
- **WHEN** `mrr(expected, retrieved)` is called
- **THEN** the result is `0.0`

### Requirement: Both metrics handle an empty retrieval without raising
`recall_at_k` and `mrr` SHALL both return `0.0`, not raise, when called
with a non-empty `expected` and an empty `retrieved` list.

#### Scenario: an empty retrieval yields 0.0 for recall_at_k
- **GIVEN** `expected` containing at least one document id
- **AND** `retrieved` is an empty list
- **WHEN** `recall_at_k(expected, retrieved, k=5)` is called
- **THEN** the result is `0.0`
- **THEN** no exception is raised

#### Scenario: an empty retrieval yields 0.0 for mrr
- **GIVEN** `expected` containing at least one document id
- **AND** `retrieved` is an empty list
- **WHEN** `mrr(expected, retrieved)` is called
- **THEN** the result is `0.0`
- **THEN** no exception is raised

### Requirement: Both metrics treat an empty expectation as trivially satisfied
`recall_at_k` and `mrr` SHALL both return `1.0` when `expected` is
empty, regardless of `retrieved`'s contents — the negative-category
case, where nothing relevant existed to find.

#### Scenario: no expected documents scores 1.0 when nothing relevant is returned
- **GIVEN** `expected` is an empty list
- **AND** `retrieved` is empty or contains only unrelated document ids
- **WHEN** `recall_at_k(expected, retrieved, k=5)` is called
- **THEN** the result is `1.0`

#### Scenario: mrr on an empty expectation is also trivially satisfied
- **GIVEN** `expected` is an empty list
- **AND** `retrieved` is empty or contains only unrelated document ids
- **WHEN** `mrr(expected, retrieved)` is called
- **THEN** the result is `1.0`

### Requirement: Both metrics handle multiple expected documents
`recall_at_k` and `mrr` SHALL both accept `expected` containing more
than one document id, without requiring every expected id to be
present.

#### Scenario: mrr with multiple expected documents uses the earliest match
- **GIVEN** `expected` containing two document ids
- **AND** `retrieved` containing the second of those two ids at
  position 1 and the first at position 4
- **WHEN** `mrr(expected, retrieved)` is called
- **THEN** the result is `1/1`
