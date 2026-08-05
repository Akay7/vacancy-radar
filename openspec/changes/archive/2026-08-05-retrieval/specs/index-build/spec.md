## ADDED Requirements

### Requirement: Table creation stamps the active build's embedding model into schema metadata
`build_index` SHALL, whenever it creates a table (a fresh build, or a
dimension-mismatch recreate), stamp the `model_name` it was called with
into the new table's schema metadata. `build_index` SHALL NOT alter an
existing, reused table's recorded metadata.

#### Scenario: a fresh build records the model it was called with
- **GIVEN** an index path with no existing table
- **WHEN** `build_index` is called with a given `model_name`
- **THEN** the resulting table's schema metadata records that
  `model_name`

#### Scenario: a dimension-driven recreate records the new model
- **GIVEN** an existing table built for one embedding model, and
  `build_index` called again with a different `model_name` whose vector
  dimension differs from the existing table's
- **WHEN** `build_index` runs (triggering the existing dimension-mismatch
  recreate path)
- **THEN** the recreated table's schema metadata records the new
  `model_name`, not the old one

#### Scenario: an incremental build with no dimension change leaves recorded metadata untouched
- **GIVEN** an existing table already recording a `model_name`
- **WHEN** `build_index` is called again with the same `model_name` (no
  table recreation)
- **THEN** the table's schema metadata still records the original
  `model_name`, unchanged
