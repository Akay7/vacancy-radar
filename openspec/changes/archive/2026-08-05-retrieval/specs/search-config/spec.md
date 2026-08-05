## ADDED Requirements

### Requirement: SearchConfig holds the configurable search defaults
`SearchConfig` SHALL hold `default_mode`, `default_vector_weight`,
`default_limit`, and `fusion_strategy` as its fields, each with a
concrete default value.

#### Scenario: SearchConfig constructs with its documented defaults
- **GIVEN** no arguments
- **WHEN** `SearchConfig()` is constructed
- **THEN** `default_mode`, `default_vector_weight`, `default_limit`, and
  `fusion_strategy` each hold their documented default value

### Requirement: resolve_search_config resolves defaults from environment variables, falling back to SearchConfig's field defaults
`resolve_search_config` SHALL read `SEARCH_DEFAULT_MODE`,
`SEARCH_DEFAULT_VECTOR_WEIGHT`, `SEARCH_DEFAULT_LIMIT`, and
`SEARCH_FUSION_STRATEGY` from the environment when present, and SHALL
fall back to `SearchConfig`'s field defaults for any that are unset.

#### Scenario: an unset environment produces SearchConfig's field defaults
- **GIVEN** none of the four environment variables are set
- **WHEN** `resolve_search_config` is called
- **THEN** the returned `SearchConfig` equals `SearchConfig()`

#### Scenario: a set environment variable overrides its corresponding default
- **GIVEN** `SEARCH_DEFAULT_LIMIT` set to a value different from
  `SearchConfig`'s field default
- **WHEN** `resolve_search_config` is called
- **THEN** the returned `SearchConfig.default_limit` equals the
  environment variable's value, not the field default

### Requirement: Changing configured defaults takes effect without editing search.py
`search()`'s effective `mode`, `vector_weight`, or `limit` SHALL change
on the next call when set via an environment variable read by
`resolve_search_config`, for any of those parameters left unspecified by
the caller — with no change to `src/vacancy_radar/index/search.py`.

#### Scenario: an environment override changes search's effective default limit
- **GIVEN** `SEARCH_DEFAULT_LIMIT` set to a value different from the
  built-in default, and no `search.py` source changes
- **WHEN** `search` is called with `limit` left unspecified
- **THEN** the number of hits returned respects the environment-
  overridden default limit (bounded by however many documents match)

### Requirement: An explicit search() argument overrides the configured default for that call only
`search` SHALL use an explicit `mode`, `limit`, or `vector_weight`
argument for that call, regardless of what `resolve_search_config`
would otherwise resolve.

#### Scenario: an explicit limit overrides the configured default
- **GIVEN** a configured default limit different from a chosen explicit
  value
- **WHEN** `search` is called with `limit` set explicitly to that chosen
  value
- **THEN** the call respects the explicit value, not the configured
  default
