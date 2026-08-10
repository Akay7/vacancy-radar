## MODIFIED Requirements

### Requirement: the tool list contains exactly the eleven specified tools, excluding reindex and any import/exec/query tool
The server's `tools/list` response SHALL list exactly
`list_vacancies`, `get_company`, `get_vacancy`, `search`,
`read_document`, `resolve`, `find_existing`, `append_note`,
`set_status`, `add_document`, `create_vacancy` — eleven tools, no more,
no fewer. It SHALL NOT list `reindex`, any stage-9-style bulk migration
capability beyond `create_vacancy` itself, or any generic
query/eval/exec tool.

#### Scenario: the tool list is exactly the eleven specified tools
- **WHEN** the server's `tools/list` response is fetched
- **THEN** the set of listed tool names equals exactly
  `{list_vacancies, get_company, get_vacancy, search, read_document,
  resolve, find_existing, append_note, set_status, add_document,
  create_vacancy}`

#### Scenario: reindex is absent
- **WHEN** the server's `tools/list` response is fetched
- **THEN** no listed tool is named `reindex`, and no listed tool
  accepts a generic query, expression, or code argument

#### Scenario: create_vacancy and find_existing are present
- **WHEN** the server's `tools/list` response is fetched
- **THEN** tools named `create_vacancy` and `find_existing` are both
  present in the listed set
