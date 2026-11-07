## ADDED Requirements

### Requirement: the MCP Apps extension is registered and advertised
The server SHALL build its `FastMCP` server with the MCP Apps
extension active, so the server advertises the
`io.modelcontextprotocol/ui` extension in its capabilities. There SHALL
be no configuration option to enable or disable this.

#### Scenario: capability advertised
- **WHEN** the server is built and its advertised capabilities are
  inspected
- **THEN** the `io.modelcontextprotocol/ui` extension is present

#### Scenario: no toggle in the CLI
- **WHEN** `vacancy-radar-mcp --help` is inspected
- **THEN** it exposes no option to turn the UI extension on or off

### Requirement: four read tools carry a ui:// view reference
The server SHALL give `list_vacancies`, `get_vacancy`, `get_company`,
and `search` each a `_meta.ui.resourceUri` pointing at a registered
`ui://` resource, and SHALL NOT give any other tool a `_meta.ui` entry.

#### Scenario: the four tools reference a registered view
- **WHEN** `tools/list` is fetched
- **THEN** `list_vacancies`, `get_vacancy`, `get_company`, and `search`
  each have `_meta.ui.resourceUri` set to a `ui://` URI, and each such
  URI matches a resource listed by the server

#### Scenario: write tools carry no ui:// reference
- **WHEN** `tools/list` is fetched
- **THEN** none of `append_note`, `set_status`, `edit_vacancy`,
  `add_document`, `create_vacancy`, `read_document`, `resolve`,
  `find_existing` has a `_meta.ui` entry

### Requirement: each ui:// resource is served as an MCP app document
Every `ui://` resource the server registers SHALL be served with the
`text/html;profile=mcp-app` MIME type and its body SHALL be a
standalone HTML document.

#### Scenario: ui:// resources have the app MIME type
- **WHEN** each registered `ui://` resource is read
- **THEN** its MIME type is `text/html;profile=mcp-app` and its body
  parses as an HTML document with a single root `<html>` element

### Requirement: ui:// resources are self-contained and make no network requests
Every `ui://` resource body SHALL contain no `<script src>`, no
`<link rel="stylesheet" href>`, no other external subresource
reference, and no `fetch`/`XMLHttpRequest`/`WebSocket` call, and SHALL
be registered with a Content-Security-Policy that permits no connect,
resource, or frame domains.

#### Scenario: no external references in a view body
- **WHEN** each registered `ui://` resource body is inspected
- **THEN** it contains no `src=` or `href=` attribute with an `http://`,
  `https://`, or `//` value, and no `fetch(`, `XMLHttpRequest`, or
  `new WebSocket` token

#### Scenario: the view's CSP permits no external domains
- **WHEN** each registered `ui://` resource's `_meta.ui.csp` is
  inspected
- **THEN** its connect, resource, and frame domain lists are each empty
  or unset

### Requirement: a ui:// view contains no vault business logic
A `ui://` resource SHALL render only fields already present in the
result of the tool that references it, and SHALL NOT compute status
transitions, resolve entities, filter, sort beyond presentation
grouping, or otherwise reproduce a `core.py` rule.

#### Scenario: the vacancy-detail view renders only fields from get_vacancy's result
- **GIVEN** a `get_vacancy` result for a fixture vacancy
- **WHEN** the `ui://vacancy-radar/vacancy-detail` view renders it
- **THEN** every value shown corresponds to a field of that result
  (id, role, company, status, source_url, found_date, applied_date,
  recruiter, stage_note, salary_note, external_id, tags, and each
  document's id/kind/title/date/path), and no document body text is
  shown

### Requirement: UI-bound tools return identical output regardless of client Apps support
Each of the four UI-bound tools SHALL return the same serialized result
content whether or not the connected client negotiated the Apps
extension, and that content SHALL equal what the same tool returned for
the same arguments before this change — the `_meta.ui` reference on the
tool definition SHALL be the only addition.

#### Scenario: result content is unchanged for a non-Apps client
- **GIVEN** the fixture vault
- **WHEN** `list_vacancies`, `get_vacancy`, `get_company`, and `search`
  are each called by a client that does not advertise the Apps
  extension
- **THEN** each tool's serialized result content is byte-for-byte equal
  to that tool's serialized result for the same arguments with the Apps
  extension not registered

#### Scenario: result content is unchanged for an Apps client
- **WHEN** a UI-bound tool is called by a client that advertises the
  Apps extension and by one that does not
- **THEN** the tool's serialized result content is identical for both,
  differing only in the presence of the `_meta.ui` reference on the
  tool definition
