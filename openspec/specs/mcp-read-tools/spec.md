# mcp-read-tools

## Purpose
Defines the MCP server's seven read-only tools — `list_vacancies`,
`get_company`, `get_vacancy`, `search`, `read_document`, `resolve`,
`find_existing` — each a thin delegation to a single `core.py` call, with
schemas that mirror `core.py`'s own parameter names, defaults, and
`models.py`-derived enums.

## Requirements

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

### Requirement: enum-typed read tool parameters enumerate permitted values from models.py
An enum-typed read tool parameter SHALL declare its permitted values
from `models.py`/`index.search` — `status` (`list_vacancies`/`search`)
from `Status`, `mode` (`search`) from `SearchMode`, `kind` (`search`)
from `DocumentKind` — never a literal list written into the server
module.

#### Scenario: search tool's status enum matches Status's members
- **WHEN** the `search` tool's schema is inspected
- **THEN** its `status` parameter's `enum` values equal
  `[s.value for s in Status]` exactly

#### Scenario: search tool's mode enum matches SearchMode's members
- **WHEN** the `search` tool's schema is inspected
- **THEN** its `mode` parameter's `enum` values equal
  `[m.value for m in SearchMode]` exactly

### Requirement: optional read tool parameters are genuinely optional
A read tool parameter SHALL stay optional in the tool's schema whenever
it is optional in `core.py`'s own signature, and omitting it SHALL
produce the same `core.py` call as passing `core.py`'s own default for
that parameter.

#### Scenario: omitting list_vacancies's limit matches core's own default
- **GIVEN** `core.list_vacancies` is mocked
- **WHEN** the `list_vacancies` tool is called with no `limit` argument
- **THEN** `core.list_vacancies` is called without a `limit` keyword
  argument (or with `limit=core.DEFAULT_LIST_LIMIT`), matching what an
  omitted `limit` already means when calling `core.list_vacancies`
  directly

#### Scenario: omitting search's mode matches core's own default resolution
- **GIVEN** `core.search` is mocked
- **WHEN** the `search` tool is called with no `mode` argument
- **THEN** `core.search` is called with `mode=None`, letting
  `core.search` resolve its own configured default, exactly as an
  unset `mode` already behaves when calling `core.search` directly

### Requirement: an out-of-range read tool argument returns a typed error, not a raised exception
A read tool call SHALL, when an argument is outside its declared enum
or otherwise rejected by `core.py`, produce a tool result reporting the
typed error rather than raising an unhandled exception out of the tool
handler.

#### Scenario: search with an unresolvable company filter returns a typed error result
- **GIVEN** `core.search` is mocked to raise `core.EntityNotFoundError`
- **WHEN** the `search` tool is called with `company="no-such-company"`
- **THEN** the tool call returns without raising, and the tool result
  reports an error naming `EntityNotFoundError`

### Requirement: the seven read tools carry readOnlyHint true
Each read tool SHALL declare `annotations.readOnlyHint = true`:
`list_vacancies`, `get_company`, `get_vacancy`, `search`,
`read_document`, `resolve`, and `find_existing`.

#### Scenario: every read tool's annotations report readOnlyHint true
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of the seven read tools' `annotations.readOnlyHint` is
  `true`

### Requirement: get_company returns counts and paths, never document bodies
The `get_company` tool's result SHALL carry each vacancy's document
count and paths (via `VacancySummary`/`DocumentSummary`) and SHALL NOT
carry any document's full text.

#### Scenario: a company with several vacancies returns no document bodies
- **GIVEN** a vault company with three vacancies, each with at least
  one document
- **WHEN** the `get_company` tool is called with that company's name
- **THEN** the tool result includes each vacancy's document count and,
  for `get_vacancy`-level detail, each document's path, and no field of
  the result contains a document's body text

### Requirement: search returns snippets and paths, never full documents
The `search` tool's result SHALL carry each hit's snippet and path and
SHALL NOT carry a hit's full document text.

#### Scenario: a search result contains snippets, not full document bodies
- **WHEN** the `search` tool is called with a query matching at least
  one indexed document
- **THEN** each hit in the tool result includes a `snippet` and a
  `path`, and no hit includes the full text of its underlying document

### Requirement: a result set at maximum limit stays within a stated size bound
The `search` and `list_vacancies` tools SHALL, at their maximum
permitted `limit`, return a tool result whose serialized size stays
within a stated bound documented alongside the tool's schema.

#### Scenario: search at maximum limit stays within the stated bound
- **WHEN** the `search` tool is called with `limit` at its maximum
  permitted value against a vault with at least that many matching
  documents
- **THEN** the serialized tool result's size does not exceed the bound
  stated in the tool's description

### Requirement: read_document rejects a path outside the vault
The `read_document` tool SHALL return a typed-error tool result, not a
file's contents, when `path` resolves outside the active vault.

#### Scenario: a path escaping the vault is rejected
- **GIVEN** a vault at `/vault` with a file at `/outside/secret.md`
- **WHEN** the `read_document` tool is called with a `path` that
  resolves to `/outside/secret.md` (e.g. via `../` segments)
- **THEN** the tool result reports a typed error (`PathOutsideVaultError`)
  and does not include that file's contents

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

### Requirement: find_existing tool's source_url parameter is optional
Calling the `find_existing` tool with no `source_url` argument SHALL
still return matches from the company tier, mirroring
`core.find_existing`'s own optional default.

#### Scenario: Omitting source_url through the tool still matches by company
- **GIVEN** a vault company with vacancies
- **WHEN** the `find_existing` tool is called with that company's name
  and no `source_url` argument
- **THEN** the tool result contains that company's vacancies

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
