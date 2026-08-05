## ADDED Requirements

### Requirement: Keyword mode returns a company's documents for its exact name
`search(index, query, mode=SearchMode.KEYWORD)` SHALL, given a query
equal to a company's exact name, return that company's documents among
the results.

#### Scenario: an exact company name returns that company's documents
- **GIVEN** a fixture company with a known exact name
- **WHEN** `search` is called with that name as the query, `mode=KEYWORD`
- **THEN** the results include at least one document belonging to that
  company

### Requirement: Keyword mode ranks a term's unique document first
`search` SHALL, under `mode=KEYWORD`, rank first the sole document
containing a distinctive proper noun that appears in exactly one
document across the fixture vault.

#### Scenario: a distinctive proper noun ranks its sole document first
- **GIVEN** a fixture document containing a distinctive proper noun that
  appears nowhere else in the fixture vault
- **WHEN** `search` is called with that proper noun as the query,
  `mode=KEYWORD`
- **THEN** that document is the first result

### Requirement: Keyword mode distinguishes a rare term from adjacent topics
A query for a rare technology term SHALL return only documents
containing that term, excluding documents that discuss a related but
distinct topic without containing the term itself.

#### Scenario: a rare term excludes documents on an adjacent topic
- **GIVEN** one fixture document containing a rare technology term and a
  second fixture document containing a different, topically adjacent
  term but not the rare term itself
- **WHEN** `search` is called with the rare term as the query,
  `mode=KEYWORD`
- **THEN** the results include the first document
- **THEN** the results do not include the second document

### Requirement: A keyword query matching nothing returns an empty result set
A well-formed keyword query with no matching document SHALL return a
`SearchResults` with an empty `hits` list, not raise an error.

#### Scenario: no matches returns empty, not an error
- **GIVEN** a query string that matches no document's text anywhere in
  the fixture vault
- **WHEN** `search` is called with that query, `mode=KEYWORD`
- **THEN** `SearchResults.hits` is empty
- **THEN** no exception is raised

### Requirement: Keyword mode scores are BM25-derived and descending
Every hit's `score` in keyword mode SHALL come from LanceDB's BM25 full-
text score, and `SearchResults.hits` SHALL be ordered by `score`
descending.

#### Scenario: keyword scores are non-increasing across the result list
- **GIVEN** a keyword query returning more than one hit
- **WHEN** the results are inspected in order
- **THEN** each hit's `score` is greater than or equal to the next hit's
  `score`

### Requirement: Semantic mode retrieves a paraphrase sharing no content words
`search(index, query, mode=SearchMode.SEMANTIC)` SHALL return a target
document for a query that is a paraphrase of that document's content
sharing no content words with it — a case keyword mode structurally
cannot serve.

#### Scenario: a content-word-free paraphrase still returns its target
- **GIVEN** a fixture document phrased in domain-specific language, and a
  paraphrase query string sharing no content words with that document's
  text
- **WHEN** `search` is called with the paraphrase query, `mode=SEMANTIC`
- **THEN** the target document is among the results
- **THEN** `search` called with the same paraphrase query and
  `mode=KEYWORD` does not return the target document

### Requirement: Semantic and hybrid queries embed with the index's recorded model, never a default
`search` SHALL, for `mode=SEMANTIC` or `mode=HYBRID`, embed the query
text using the embedding model name recorded in the index's schema
metadata, and SHALL raise `EmbeddingModelMismatchError` naming both the
recorded model and the codebase's currently configured default model
before embedding anything, when the two disagree (including when the
index records no model at all).

#### Scenario: the query is embedded with the recorded model
- **GIVEN** an index built with a known embedding model, recorded in its
  schema metadata, matching the codebase's current default
- **WHEN** `search` is called with `mode=SEMANTIC`
- **THEN** the query is embedded using the recorded model
- **THEN** `search` completes without raising

#### Scenario: a recorded model that disagrees with the current default raises
- **GIVEN** an index whose recorded embedding model differs from the
  codebase's currently configured default embedding model
- **WHEN** `search` is called with `mode=SEMANTIC` or `mode=HYBRID`
- **THEN** `EmbeddingModelMismatchError` is raised
- **THEN** the error names both the recorded model and the configured
  default model
- **THEN** no embedding call is made

#### Scenario: an index with no recorded model raises the same typed error
- **GIVEN** an index built before embedding-model provenance was
  recorded (no `embedding_model` in schema metadata)
- **WHEN** `search` is called with `mode=SEMANTIC` or `mode=HYBRID`
- **THEN** `EmbeddingModelMismatchError` is raised, naming the configured
  default model and indicating no model is recorded

### Requirement: Hybrid mode's results are the union of the keyword and semantic candidate sets
`search(index, query, mode=SearchMode.HYBRID)` SHALL return a result set
whose members each appear in the keyword candidate set, the semantic
candidate set, or both.

#### Scenario: every hybrid hit appears in at least one single-mode result set
- **GIVEN** a query returning results under `mode=KEYWORD`,
  `mode=SEMANTIC`, and `mode=HYBRID`
- **WHEN** the hybrid results are inspected
- **THEN** every hybrid hit's `doc_id` appears in the keyword results,
  the semantic results, or both

### Requirement: A document strong in both hybrid paths outranks one strong in only one
`search` under `mode=HYBRID` SHALL rank a document that scores highly in
both the keyword and semantic candidate sets above a document that
scores highly in only one of them.

#### Scenario: a dual-path match outranks a single-path match
- **GIVEN** a query for which one fixture document ranks highly under
  both `mode=KEYWORD` and `mode=SEMANTIC`, and a second fixture document
  ranks highly under only one of those modes
- **WHEN** `search` is called with `mode=HYBRID`
- **THEN** the dual-path document is ranked above the single-path
  document

### Requirement: vector_weight under Linear Combination fusion changes hybrid ordering, degenerating at the extremes
`search` SHALL, under `mode=HYBRID` with `SearchConfig.fusion_strategy`
set to Linear Combination, produce a different hit ordering for
different `vector_weight` values, approximating `mode=SEMANTIC`'s
ordering as `vector_weight` approaches 1 and `mode=KEYWORD`'s ordering
as `vector_weight` approaches 0.

#### Scenario: changing vector_weight changes the ordering
- **GIVEN** a hybrid query under Linear Combination fusion, run once with
  a low `vector_weight` and once with a high `vector_weight`
- **WHEN** the two result orderings are compared
- **THEN** the orderings differ

#### Scenario: extreme vector_weight values approximate single-mode orderings
- **GIVEN** the same hybrid query run under Linear Combination fusion
  with `vector_weight` near 0 and near 1
- **WHEN** each is compared to `mode=KEYWORD`'s and `mode=SEMANTIC`'s
  respective orderings for the same query
- **THEN** the `vector_weight` near 0 ordering approximates the keyword
  ordering
- **THEN** the `vector_weight` near 1 ordering approximates the semantic
  ordering

### Requirement: Each hybrid hit reports its per-path rank, null when absent from that path
Every `SearchHit` under `mode=HYBRID` SHALL report `keyword_rank` as its
1-based position in the keyword candidate set, or `None` if it did not
appear there, and `semantic_rank` likewise for the semantic candidate
set — independent of which fusion strategy combined them.

#### Scenario: a hit present in both paths reports both ranks
- **GIVEN** a hybrid query where one result appears in both the keyword
  and semantic candidate sets
- **WHEN** that hit is inspected
- **THEN** its `keyword_rank` and `semantic_rank` are both non-null
  integers

#### Scenario: a hit present in only one path reports null for the other
- **GIVEN** a hybrid query where one result appears in only the semantic
  candidate set
- **WHEN** that hit is inspected
- **THEN** its `semantic_rank` is a non-null integer
- **THEN** its `keyword_rank` is `None`

### Requirement: company_slug restricts results to that company
`search` given `company_slug` SHALL return only documents whose
`company_slug` matches, excluding every other company's documents.

#### Scenario: company_slug excludes other companies
- **GIVEN** the fixture vault has documents from at least two companies
- **WHEN** `search` is called with `company_slug` set to one company's
  slug
- **THEN** every hit's `company_slug` equals the given slug
- **THEN** no hit belongs to a different company

### Requirement: status accepts multiple values and returns their union
`search` given a `status` list SHALL return documents whose `status` is
any of the given values.

#### Scenario: status filter returns the union of the given statuses
- **GIVEN** fixture documents with at least two distinct statuses
- **WHEN** `search` is called with `status` set to a list containing two
  status values
- **THEN** every hit's `status` is one of the two given values
- **THEN** hits with both given statuses are present when documents with
  each exist

### Requirement: kind restricts results to the given document kinds
`search` given a `kind` list SHALL return only documents whose `kind` is
in that list.

#### Scenario: kind filter excludes other document kinds
- **GIVEN** fixture documents of at least two distinct kinds
- **WHEN** `search` is called with `kind` set to a list containing one
  kind
- **THEN** every hit's `kind` is in the given list

### Requirement: tags restricts results to documents carrying at least one given tag
`search` given a `tags` list SHALL return only documents whose `tags`
column contains at least one of the given values.

#### Scenario: tags filter excludes documents with none of the given tags
- **GIVEN** a fixture document tagged with a known tag, and another
  fixture document without that tag
- **WHEN** `search` is called with `tags` set to a list containing that
  tag
- **THEN** the tagged document is among the results
- **THEN** the untagged document is not among the results

### Requirement: since excludes documents dated earlier
`search` given `since` SHALL return only documents whose `date` is on or
after `since`.

#### Scenario: since excludes earlier-dated documents
- **GIVEN** fixture documents with dates before and after a chosen cutoff
- **WHEN** `search` is called with `since` set to that cutoff
- **THEN** every hit's `date` is on or after the cutoff

### Requirement: Combined filters compose as AND
`search` given more than one filter parameter SHALL return only
documents satisfying every given filter simultaneously.

#### Scenario: two filters combine as AND, not OR
- **GIVEN** a query where `company_slug` alone and `status` alone each
  match documents the other excludes
- **WHEN** `search` is called with both filters set together
- **THEN** every hit satisfies both filters
- **THEN** no hit satisfies only one of the two filters

### Requirement: A filter matching nothing returns empty, not an error
`search` given a filter combination matching no document SHALL return an
empty `hits` list without raising.

#### Scenario: an impossible filter combination returns empty
- **GIVEN** a `company_slug`/`status` combination that matches no
  fixture document
- **WHEN** `search` is called with that combination
- **THEN** `SearchResults.hits` is empty
- **THEN** no exception is raised

### Requirement: Filtering does not reduce the result count below limit when enough matches exist
`search` given a filter and a `limit` SHALL return exactly `limit` hits
whenever at least `limit` documents satisfy that filter, proving the
filter is pushed into the query as a predicate rather than applied to an
already-truncated result set.

#### Scenario: a filter with enough matches still fills the limit
- **GIVEN** a filter matched by more documents than a chosen `limit`
- **WHEN** `search` is called with that filter and that `limit`
- **THEN** exactly `limit` hits are returned

### Requirement: Identical queries return identical ordering
`search` SHALL return hits in the same order across repeated calls made
with the same arguments against an unmodified index.

#### Scenario: repeating the same query reproduces the same order
- **GIVEN** a query executed once against the fixture index
- **WHEN** the identical call is repeated
- **THEN** the two calls' `hits` lists have the same `doc_id`s in the
  same order

### Requirement: Ties break deterministically
When two or more hits share the same `score`, `search` SHALL order them
by a fixed, deterministic secondary key (`doc_id` ascending) rather than
by an order that can vary between calls.

#### Scenario: equal-score hits are ordered by doc_id
- **GIVEN** a query where at least two hits have an identical `score`
- **WHEN** the results are inspected across repeated calls
- **THEN** the tied hits appear in the same relative order every time,
  ascending by `doc_id`

### Requirement: An empty query string raises a typed error
`search` called with an empty or whitespace-only query string SHALL
raise `EmptyQueryError` rather than querying the index.

#### Scenario: an empty query raises EmptyQueryError
- **GIVEN** a query string that is empty or contains only whitespace
- **WHEN** `search` is called with that query
- **THEN** `EmptyQueryError` is raised

### Requirement: A query against an index with no FTS index raises a typed error naming the fix
`search` SHALL raise `MissingFTSIndexError`, naming `build_index` as the
fix, when `mode=KEYWORD` or `mode=HYBRID` runs against a table with no
full-text index on `text` — rather than letting the underlying LanceDB
error propagate.

#### Scenario: no FTS index raises MissingFTSIndexError naming the fix
- **GIVEN** a LanceDB table with no full-text index created on `text`
- **WHEN** `search` is called with `mode=KEYWORD` or `mode=HYBRID`
- **THEN** `MissingFTSIndexError` is raised
- **THEN** its message names `build_index` as the fix

### Requirement: limit=0 returns empty; a negative limit raises
`search` called with `limit=0` SHALL return an empty `hits` list without
raising. `search` called with a negative `limit` SHALL raise
`InvalidLimitError`.

#### Scenario: limit=0 returns an empty result set
- **GIVEN** a query that would otherwise return results
- **WHEN** `search` is called with `limit=0`
- **THEN** `SearchResults.hits` is empty
- **THEN** no exception is raised

#### Scenario: a negative limit raises InvalidLimitError
- **GIVEN** any well-formed query
- **WHEN** `search` is called with a negative `limit`
- **THEN** `InvalidLimitError` is raised

### Requirement: An over-length query is truncated with a warning, not an error
`search` SHALL emit a warning and proceed, rather than raising, when
`mode=SEMANTIC` or `mode=HYBRID` is called with a query longer than a
configured word-count threshold (the embedding model truncates
internally).

#### Scenario: a very long query warns and still returns results
- **GIVEN** a query string far exceeding the configured word-count
  threshold
- **WHEN** `search` is called with `mode=SEMANTIC`
- **THEN** a warning is emitted
- **THEN** `search` completes without raising and returns results

### Requirement: Search over a large index completes within a practical time budget
`search` SHALL complete within a few hundred milliseconds when run
against an index built from a ~700-vacancy generated vault, for each of
`mode=KEYWORD`, `mode=SEMANTIC`, and `mode=HYBRID`.

#### Scenario: a query over a large index returns within budget
- **GIVEN** an index built from a generated ~700-vacancy vault
- **WHEN** `search` is called, timed, for each mode
- **THEN** each call completes within a few hundred milliseconds

### Requirement: Keyword mode never loads the embedding model
`search` under `mode=KEYWORD` SHALL never trigger loading of the
embedding model, regardless of query content or filters.

#### Scenario: a keyword query loads no embedding model
- **GIVEN** the embedding model has not yet been loaded in the current
  process
- **WHEN** `search` is called with `mode=KEYWORD` (instrumented to detect
  a model load)
- **THEN** no embedding model load occurs
