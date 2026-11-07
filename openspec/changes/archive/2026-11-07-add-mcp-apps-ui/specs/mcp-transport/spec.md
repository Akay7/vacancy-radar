## MODIFIED Requirements

### Requirement: the tool list contains exactly the eleven specified tools, excluding reindex and any import/exec/query tool
The server's `tools/list` response SHALL list exactly
`list_vacancies`, `get_company`, `get_vacancy`, `search`,
`read_document`, `resolve`, `find_existing`, `append_note`,
`set_status`, `edit_vacancy`, `add_document`, `create_vacancy` — twelve
tools, no more, no fewer. It SHALL NOT list `reindex`, any
stage-9-style bulk migration capability beyond `create_vacancy` itself,
or any generic query/eval/exec tool. Adding a `_meta.ui` reference to a
tool (see `mcp-apps-ui`) SHALL NOT add, remove, or rename any tool in
this set.

(The count and the `edit_vacancy` entry correct a stale "eleven" in
this requirement: `edit_vacancy` was added in v0.2.0 and the server and
its tests already expect twelve.)

#### Scenario: the tool list is exactly the twelve specified tools
- **WHEN** the server's `tools/list` response is fetched
- **THEN** the set of listed tool names equals exactly
  `{list_vacancies, get_company, get_vacancy, search, read_document,
  resolve, find_existing, append_note, set_status, edit_vacancy,
  add_document, create_vacancy}`

#### Scenario: reindex is absent
- **WHEN** the server's `tools/list` response is fetched
- **THEN** no listed tool is named `reindex`, and no listed tool
  accepts a generic query, expression, or code argument

#### Scenario: create_vacancy and find_existing are present
- **WHEN** the server's `tools/list` response is fetched
- **THEN** tools named `create_vacancy` and `find_existing` are both
  present in the listed set

#### Scenario: a _meta.ui entry does not change the tool set
- **WHEN** the server's `tools/list` response is fetched
- **THEN** the set of listed tool names equals exactly the twelve
  specified tools, and every name that carries a `_meta.ui` entry is
  one of those twelve

### Requirement: every exposed tool carries openWorldHint false
Every tool the server lists SHALL declare
`annotations.openWorldHint = false`, whether or not it also carries a
`_meta.ui` reference.

#### Scenario: every listed tool's annotations report openWorldHint false
- **WHEN** the server's `tools/list` response is fetched
- **THEN** every listed tool's `annotations.openWorldHint` is `false`

#### Scenario: a UI-bound tool still reports its hints
- **WHEN** the server's `tools/list` response is fetched
- **THEN** each of `list_vacancies`, `get_vacancy`, `get_company`, and
  `search` reports `annotations.openWorldHint = false` and
  `annotations.readOnlyHint = true`

### Requirement: server startup completes fast enough not to delay client launch
Server initialization, measured with no embedding model present, SHALL
complete within a stated time bound, with the Apps extension and its
`ui://` resources registered.

#### Scenario: startup time is measured and bounded
- **GIVEN** no embedding model is cached or loaded
- **WHEN** the server process is started and initialization is timed
  end to end
- **THEN** initialization completes within the bound stated in
  tasks.md's manual verification notes, with the four `ui://` resources
  registered
