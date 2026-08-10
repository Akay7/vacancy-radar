## ADDED Requirements

### Requirement: find_existing tool's source_url parameter is optional
Calling the `find_existing` tool with no `source_url` argument SHALL
still return matches from the company tier, mirroring
`core.find_existing`'s own optional default.

#### Scenario: Omitting source_url through the tool still matches by company
- **GIVEN** a vault company with vacancies
- **WHEN** the `find_existing` tool is called with that company's name
  and no `source_url` argument
- **THEN** the tool result contains that company's vacancies
