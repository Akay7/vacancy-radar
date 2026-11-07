# mcp-transport

## Purpose
Defines the MCP server's stdio transport hygiene, startup performance, and
tool-surface shape: clean JSON-RPC framing on stdout, diagnostics on
stderr, no eager embedding-model load, `openWorldHint=false` on every tool,
exactly the eleven specified tools, and typed errors surfaced as tool
results rather than protocol-level errors.

## Requirements

### Requirement: nothing is written to stdout except JSON-RPC frames
The server SHALL, across a full tool exchange, write nothing to stdout
except bytes that parse as JSON-RPC protocol frames — no stray print
output, warning, or log line.

#### Scenario: stdout across a full tool exchange parses as protocol frames only
- **GIVEN** the server process's stdout is captured across
  initialization and one full tool call/response exchange
- **WHEN** the captured stdout is split into lines and each is parsed
- **THEN** every line parses successfully as a JSON-RPC frame, and no
  line fails to parse

### Requirement: diagnostics go to stderr
The server SHALL write any warning, log message, or diagnostic it or a
dependency emits during a tool call to stderr, never stdout.

#### Scenario: a warning raised during a tool call appears on stderr, not stdout
- **GIVEN** a tool call that triggers a Python `warnings.warn` (e.g. an
  over-length search query, per `index.search`'s own query-length
  warning)
- **WHEN** the call is made with stdout and stderr captured separately
- **THEN** the warning text appears on stderr, and stdout still parses
  as protocol frames only

### Requirement: the embedding model is not loaded at server start
Server initialization SHALL complete without loading or downloading
the `fastembed` embedding model.

#### Scenario: server startup does not trigger a model load
- **GIVEN** no embedding model is cached locally (simulated via a
  monkeypatched loader that raises if invoked)
- **WHEN** the server initializes
- **THEN** initialization completes without the embedding-model loader
  being invoked

### Requirement: a keyword-mode search completes without loading the embedding model
The `search` tool, called with `mode="keyword"`, SHALL complete without
loading the embedding model.

#### Scenario: keyword search succeeds with the embedding loader disabled
- **GIVEN** the embedding-model loader is monkeypatched to raise if
  invoked
- **WHEN** the `search` tool is called with `mode="keyword"` against an
  indexed vault
- **THEN** the call succeeds and the embedding-model loader is never
  invoked

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

### Requirement: the tool list contains exactly the eleven specified tools, excluding reindex and any import/exec/query tool
The server's `tools/list` response SHALL list exactly
`list_vacancies`, `get_company`, `get_vacancy`, `search`,
`read_document`, `resolve`, `find_existing`, `append_note`,
`set_status`, `edit_vacancy`, `add_document`, `create_vacancy` —
twelve tools, no more, no fewer. It SHALL NOT list `reindex`, any
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

### Requirement: a core.py typed error surfaces as a structured tool-result error, not a protocol-level error
The server SHALL catch any typed error a `core.py`, `config.py`, or
`index.search` call raises during a tool invocation and return it as a
tool result with `isError=true` carrying the error's type and message,
rather than letting it propagate as an unhandled exception that becomes
a JSON-RPC protocol-level error.

#### Scenario: a typed core.py error becomes an isError tool result
- **GIVEN** `core.get_vacancy` is mocked to raise
  `core.EntityNotFoundError`
- **WHEN** the `get_vacancy` tool is called with a query that triggers
  it
- **THEN** the tool call returns a result with `isError=true` naming
  `EntityNotFoundError` and its message, and the server process does
  not crash or emit a JSON-RPC-level error response for that call
