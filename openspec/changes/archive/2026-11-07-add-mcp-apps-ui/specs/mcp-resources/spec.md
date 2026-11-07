## ADDED Requirements

### Requirement: ui:// app resources are exposed alongside the data resources
The server SHALL list its `ui://` app resources in `resources/list` in
addition to `vacancy-radar://companies` and `vacancy-radar://statuses`,
and the two data resources' URIs, content, and behaviour SHALL be
unchanged by their presence.

#### Scenario: the data resources are unchanged
- **GIVEN** the fixture vault
- **WHEN** `vacancy-radar://companies` and `vacancy-radar://statuses`
  are read
- **THEN** each resource's content is byte-for-byte equal to its
  content with the Apps extension not registered

#### Scenario: the ui:// resources are listed
- **WHEN** `resources/list` is fetched
- **THEN** it contains every `ui://` resource the four UI-bound tools
  reference

#### Scenario: ui:// resources stay out of the vacancy-radar:// scheme
- **WHEN** `resources/list` is fetched
- **THEN** no `ui://` resource uses the `vacancy-radar://` scheme, and
  `vacancy-radar://companies` and `vacancy-radar://statuses` remain the
  only two `vacancy-radar://` resources
