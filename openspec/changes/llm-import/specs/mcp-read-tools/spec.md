## MODIFIED Requirements

### Requirement: each read tool delegates to exactly one core.py function
Each read tool SHALL, with `core.py` mocked, call exactly one `core.py`
function and return that call's result unmodified apart from
serialization: `list_vacancies`, `get_company`, `get_vacancy`,
`search`, `read_document`, `resolve`, `find_existing`. Neither the tool
module nor any tool handler SHALL contain filtering, sorting, path
manipulation, or other business rules of its own.

#### Scenario: list_vacancies tool delegates to core.list_vacancies
- **GIVEN** `core.list_vacancies` is mocked to return a fixed list of
  `VacancySummary` rows
- **WHEN** the `list_vacancies` tool is called with `status=["applied"]`
- **THEN** `core.list_vacancies` is called exactly once with
  `status=["applied"]` and the tool result contains the mocked rows,
  serialized, unmodified

#### Scenario: get_company tool delegates to core.get_company
- **GIVEN** `core.get_company` is mocked to return a fixed
  `CompanyDossier`
- **WHEN** the `get_company` tool is called with `name="Acme"`
- **THEN** `core.get_company` is called exactly once with `name="Acme"`
  and the tool result matches the mocked dossier, serialized,
  unmodified

#### Scenario: get_vacancy tool delegates to core.get_vacancy
- **GIVEN** `core.get_vacancy` is mocked to return a fixed
  `VacancyDetail`
- **WHEN** the `get_vacancy` tool is called with `id_or_query="v-1"`
- **THEN** `core.get_vacancy` is called exactly once with
  `id_or_query="v-1"` and the tool result matches the mocked detail,
  serialized, unmodified

#### Scenario: search tool delegates to core.search
- **GIVEN** `core.search` is mocked to return a fixed `SearchResults`
- **WHEN** the `search` tool is called with `query="python"`,
  `mode="keyword"`
- **THEN** `core.search` is called exactly once with `query="python"`,
  `mode=SearchMode.KEYWORD`, and every other argument at its default,
  and the tool result matches the mocked hits, serialized, unmodified

#### Scenario: read_document tool delegates to core.read_document
- **GIVEN** `core.read_document` is mocked to return a fixed
  `DocumentContent`
- **WHEN** the `read_document` tool is called with
  `path="acme/v-1/documents/note.md"`
- **THEN** `core.read_document` is called exactly once with that path
  and the tool result matches the mocked content, serialized, unmodified

#### Scenario: resolve tool delegates to core.resolve
- **GIVEN** `core.resolve` is mocked to return a fixed `Resolution`
- **WHEN** the `resolve` tool is called with `query="Acme"`
- **THEN** `core.resolve` is called exactly once with `query="Acme"`
  and the tool result matches the mocked resolution, serialized,
  unmodified

#### Scenario: find_existing tool delegates to core.find_existing
- **GIVEN** `core.find_existing` is mocked to return a fixed list of
  `VacancySummary` rows
- **WHEN** the `find_existing` tool is called with `company="Acme"`,
  `source_url="https://acme.example/1"`
- **THEN** `core.find_existing` is called exactly once with
  `company="Acme"`, `source_url="https://acme.example/1"` and the tool
  result contains the mocked rows, serialized, unmodified

### Requirement: read tool argument names match core.py parameter names
Every argument a read tool's schema declares SHALL share its name with
the `core.py` parameter it is passed as — no tool SHALL rename, alias,
or restructure an argument on its way into the matching `core.py` call.

#### Scenario: list_vacancies tool argument names match core.list_vacancies's signature
- **WHEN** the `list_vacancies` tool's schema is inspected
- **THEN** its parameter names are a subset of
  `{status, company, since, stale_days, needs_review, limit}`, matching
  `core.list_vacancies`'s own keyword parameter names exactly

#### Scenario: search tool argument names match core.search's signature
- **WHEN** the `search` tool's schema is inspected
- **THEN** its parameter names are a subset of
  `{query, mode, company, status, kind, limit}` and each name that also
  appears in `core.search`'s signature (`query`, `mode`, `status`,
  `kind`, `limit`) matches it exactly; `company` maps to `core.search`'s
  `company_slug` parameter, its one intentional exception (documented
  alongside the schema)

#### Scenario: find_existing tool argument names match core.find_existing's signature
- **WHEN** the `find_existing` tool's schema is inspected
- **THEN** its parameter names are exactly `{company, source_url}`,
  matching `core.find_existing`'s own parameter names exactly

### Requirement: every read tool exposes a valid JSON schema
Each of the seven read tools SHALL declare an `inputSchema` that is
valid JSON Schema, listed in the server's `tools/list` response.

#### Scenario: every read tool's schema validates as JSON Schema
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of `list_vacancies`, `get_company`, `get_vacancy`,
  `search`, `read_document`, `resolve`, `find_existing` is present, and
  each one's `inputSchema` validates successfully against the JSON
  Schema meta-schema

### Requirement: the seven read tools carry readOnlyHint true
Each read tool SHALL declare `annotations.readOnlyHint = true`:
`list_vacancies`, `get_company`, `get_vacancy`, `search`,
`read_document`, `resolve`, and `find_existing`.

#### Scenario: every read tool's annotations report readOnlyHint true
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of the seven read tools' `annotations.readOnlyHint` is
  `true`

## ADDED Requirements

### Requirement: find_existing tool returns matches for a company that exists
The `find_existing` tool SHALL return a company's vacancies when the
given `company` resolves to that existing company.

#### Scenario: An existing company's vacancies are returned through the tool
- **GIVEN** a vault company with vacancies
- **WHEN** the `find_existing` tool is called with that company's name
  and a `source_url` matching none of them
- **THEN** the tool result contains that company's vacancies

### Requirement: find_existing tool returns an empty list for a company that does not exist
The `find_existing` tool SHALL return an empty list, not a typed
error, when `company` resolves to no company and `source_url` matches
no vacancy.

#### Scenario: A nonexistent company with no matching source_url returns empty through the tool
- **WHEN** the `find_existing` tool is called with a company name
  matching nothing in the vault and a `source_url` matching no vacancy
- **THEN** the tool result is an empty list

### Requirement: find_existing tool matches on source_url across differing company spellings
The `find_existing` tool SHALL return a vacancy whose `source_url`
matches the given `source_url`, even when the given `company` argument
does not resolve to that vacancy's own company.

#### Scenario: A differently-spelled company argument still matches through the tool
- **GIVEN** a vacancy filed under one company spelling, with a known
  `source_url`
- **WHEN** the `find_existing` tool is called with a differently-spelled
  `company` argument and that vacancy's exact `source_url`
- **THEN** the tool result contains that vacancy's summary
