# embedding Specification

## Purpose
TBD - created by openspec-sync-specs during change index-build. Update Purpose after archive.

## Requirements

### Requirement: The embedding model is not loaded at import time
`vacancy_radar.index.embed` and `vacancy_radar.index.build` SHALL NOT
instantiate or load an embedding model as a side effect of being
imported.

#### Scenario: importing build.py does not load the model
- **GIVEN** a clean process (the embedding model not yet loaded)
- **WHEN** `vacancy_radar.index.build` is imported, with model loading
  instrumented
- **THEN** no model load occurs as a result of the import

### Requirement: The model loads lazily on first use and is reused
`embed_texts` SHALL load its model on the first call for a given model
name, and SHALL reuse that loaded model on every subsequent call for
the same name without reloading it.

#### Scenario: the model loads on first call
- **GIVEN** no model yet loaded for a given model name
- **WHEN** `embed_texts` is called once with that model name
- **THEN** a model load occurs

#### Scenario: a second call with the same model name does not reload
- **GIVEN** a model already loaded for a given model name (from a
  prior `embed_texts` call)
- **WHEN** `embed_texts` is called again with that same model name
- **THEN** no additional model load occurs
- **THEN** the returned vectors have the same dimensionality as the
  first call's

### Requirement: Vector dimensionality matches the configured model
`embed_texts` SHALL return vectors whose length equals the configured
model's native output dimension.

#### Scenario: vector length matches the model's dimension
- **GIVEN** the default embedding model
- **WHEN** `embed_texts` is called with one or more texts
- **THEN** every returned vector's length equals that model's reported
  dimension

#### Scenario: changing the model name changes the returned dimension
- **GIVEN** two configured model names with different native
  dimensions
- **WHEN** `embed_texts` is called once with each model name
- **THEN** the two calls return vectors of their respective models'
  dimensions, with no manual reconfiguration beyond passing the model
  name
</content>
