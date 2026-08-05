# eval-queries

## Purpose

TBD — added by `eval-harness`. Defines the committed, labelled query
set (`eval/queries.yaml`) that the eval runner sweeps against the
fixture vault to measure retrieval quality.

## Requirements

### Requirement: queries.yaml holds 30 labelled queries against committed fixture doc_ids
`eval/queries.yaml` SHALL contain 30 query records, each with `id`,
`query`, `expected_doc_ids` (a list, empty only for `negative`),
`category`, and `note` fields, written against `tests/fixtures/vault`'s
committed content — never against real vacancy data, and never
containing a real company name.

#### Scenario: queries.yaml loads into 30 well-formed records
- **GIVEN** `eval/queries.yaml`
- **WHEN** it is parsed
- **THEN** exactly 30 records are produced
- **THEN** every record has non-empty `id`, `query`, `category`, and
  `note` fields, and an `expected_doc_ids` list (possibly empty)

### Requirement: Every category meets its stated target query count
`eval/queries.yaml` SHALL contain at least the following count of
queries per `category`: `exact_name` 5, `technical` 5, `paraphrase` 4,
`temporal` 4, `multi_result` 4, `filtered` 4, `negative` 4.

#### Scenario: each category's query count meets its target
- **GIVEN** `eval/queries.yaml`'s records grouped by `category`
- **WHEN** each category's group size is compared to its stated target
- **THEN** every category's group size is at least its target count

### Requirement: No two queries share an id
Every record's `id` in `eval/queries.yaml` SHALL be unique across the
whole file.

#### Scenario: query ids are all distinct
- **GIVEN** `eval/queries.yaml`'s records
- **WHEN** their `id` fields are collected
- **THEN** no `id` value appears more than once

### Requirement: Every expected_doc_id resolves in the fixture index
Every id listed in any record's `expected_doc_ids` SHALL exist as a
`doc_id` in the index built from `tests/fixtures/vault`. A stale id
SHALL fail this test suite rather than silently scoring zero at eval
time.

#### Scenario: a stale expected_doc_id fails the test suite
- **GIVEN** the fixture index built from `tests/fixtures/vault`
- **WHEN** every `expected_doc_ids` entry across all of
  `eval/queries.yaml`'s records is checked against that index's known
  `doc_id`s
- **THEN** every one of them is found
- **THEN** the test fails, naming the offending query id and doc id, if
  any is not found

### Requirement: filtered-category queries carry a structured filter
Every record whose `category` is `filtered` SHALL include a `filter`
mapping whose keys are a subset of `search()`'s filter parameters
(`company_slug`, `status`, `kind`, `tags`, `since`).

#### Scenario: every filtered-category query has a filter mapping
- **GIVEN** `eval/queries.yaml`'s records with `category: filtered`
- **WHEN** each is inspected
- **THEN** each has a non-empty `filter` mapping
- **THEN** every key in that mapping is one of `company_slug`,
  `status`, `kind`, `tags`, `since`

### Requirement: Paraphrase queries share no content word with their expected document
Every record whose `category` is `paraphrase` SHALL have a `query`
string sharing no content word (case-insensitive, stopwords excluded)
with the text of its `expected_doc_ids` target document(s) — verified
by test, not by the query's stated intent.

#### Scenario: a paraphrase query shares no content word with its target
- **GIVEN** a `paraphrase`-category record and the fixture document text
  for each of its `expected_doc_ids`
- **WHEN** the record's `query` content words (stopwords excluded) are
  compared against that document text's content words
- **THEN** the intersection is empty
</content>
